/*
 * bltrace_hook.c -- MSVC /Gh function-entry tracing.
 *
 * Reconstructed 2026-11-03 from the surviving bltrace_hook.obj and
 * bltrace_penter.obj in build_windows_x64_vc17_Release.
 *
 * Data written by the dump functions is a flat sequence of little-endian
 * 64-bit values:
 *   function table: rva + 1
 *   edge table:     (caller_rva << 32) | callee_rva
 *   return table:   (callee_rva << 32) | caller_rva
 * where rva is the address returned by the /Gh entry call minus the module
 * base, i.e. entry + 5 for the usual five-byte call _penter.
 */

#include <windows.h>
#include <intrin.h>
#include <stdint.h>

#define SLOT_COUNT 0x200000u
#define SLOT_MASK (SLOT_COUNT - 1u)
#define TABLE_BYTES ((size_t)SLOT_COUNT * sizeof(uint64_t))
#define STACK_CAP 0x2000

#define TIME_SLOT_COUNT 0x80000u
#define TIME_SLOT_MASK (TIME_SLOT_COUNT - 1u)
#define TIME_MAGIC 0x4D495442u /* 'BTIM' */
#define TIME_VERSION 1u

typedef struct TlsFrame {
  uint64_t rva;
  uint64_t t0;
  uint64_t child;
} TlsFrame;

typedef struct TlsStack {
  int count;
  TlsFrame stack[STACK_CAP];
} TlsStack;

typedef struct TimingSlot {
  uint64_t key; /* rva + 1; 0 = empty */
  uint64_t count;
  uint64_t self;
  uint64_t inclusive;
} TimingSlot;

typedef struct TimingRecord {
  uint64_t key;
  uint64_t count;
  uint64_t self;
  uint64_t inclusive;
} TimingRecord;

typedef struct TimingHeader {
  uint32_t magic;
  uint32_t version;
  uint64_t freq;
  uint32_t record_size;
  uint32_t count;
} TimingHeader;

static volatile LONG g_armed = 0;
static volatile LONG g_count = 0;
static volatile LONG g_ecount = 0;
static volatile LONG g_rcount = 0;
static uint64_t g_base = 0;
static uint64_t *g_slots = NULL;
static uint64_t *g_eslots = NULL;
static uint64_t *g_rslots = NULL;
static TimingSlot *g_tslots = NULL;
static volatile LONG g_tcount = 0;
static uint64_t g_qpc_freq = 0;
static DWORD g_tls = TLS_OUT_OF_INDEXES;

static __declspec(noinline) int claim(uint64_t *table, uint32_t mask, uint64_t value)
{
  uint32_t hash = (uint32_t)value * 0x9E3779B1u;
  uint32_t count = mask + 1u;
  for (uint32_t offset = 0; offset < count; offset++) {
    uint32_t index = (hash + offset) & mask;
    __int64 expected = 0;
    __int64 old = _InterlockedCompareExchange64(
        (volatile __int64 *)&table[index], (__int64)value, expected);
    if (old == 0) {
      return 1;
    }
    if ((uint64_t)old == value) {
      return 0;
    }
  }
  return 0;
}

static __declspec(noinline) TimingSlot *timing_slot(uint64_t key)
{
  if (g_tslots == NULL) {
    return NULL;
  }
  uint32_t hash = (uint32_t)key * 0x9E3779B1u;
  for (uint32_t offset = 0; offset < TIME_SLOT_COUNT; offset++) {
    uint32_t index = (hash + offset) & TIME_SLOT_MASK;
    TimingSlot *slot = &g_tslots[index];
    uint64_t current = slot->key;
    if (current == key) {
      return slot;
    }
    if (current == 0) {
      __int64 expected = 0;
      __int64 old = _InterlockedCompareExchange64(
          (volatile __int64 *)&slot->key, (__int64)key, expected);
      if (old == 0) {
        _InterlockedIncrement(&g_tcount);
        return slot;
      }
      if ((uint64_t)old == key) {
        return slot;
      }
    }
  }
  return NULL;
}

static __declspec(noinline) TlsStack *tls_state(void)
{
  if (g_tls == TLS_OUT_OF_INDEXES) {
    return NULL;
  }
  TlsStack *state = (TlsStack *)TlsGetValue(g_tls);
  if (state != NULL) {
    return state;
  }
  state = (TlsStack *)VirtualAlloc(
      NULL, sizeof(TlsStack), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
  if (state != NULL) {
    TlsSetValue(g_tls, state);
  }
  return state;
}

__declspec(dllexport) int bltrace_arm(void)
{
  if (g_base == 0) {
    g_base = (uint64_t)(uintptr_t)GetModuleHandleA(NULL);
  }
  if (g_slots == NULL) {
    g_slots = (uint64_t *)VirtualAlloc(
        NULL, TABLE_BYTES, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
  }
  if (g_eslots == NULL) {
    g_eslots = (uint64_t *)VirtualAlloc(
        NULL, TABLE_BYTES, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
  }
  if (g_rslots == NULL) {
    g_rslots = (uint64_t *)VirtualAlloc(
        NULL, TABLE_BYTES, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
  }
  if (g_tslots == NULL) {
    g_tslots = (TimingSlot *)VirtualAlloc(
        NULL, (size_t)TIME_SLOT_COUNT * sizeof(TimingSlot),
        MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
  }
  if (g_qpc_freq == 0) {
    LARGE_INTEGER freq;
    if (QueryPerformanceFrequency(&freq)) {
      g_qpc_freq = (uint64_t)freq.QuadPart;
    }
  }
  if (g_tls == TLS_OUT_OF_INDEXES) {
    g_tls = TlsAlloc();
  }
  return _InterlockedExchange(&g_armed, 1);
}

__declspec(dllexport) uint32_t bltrace_count(void)
{
  return (uint32_t)g_count;
}

__declspec(dllexport) int bltrace_disarm(void)
{
  return _InterlockedExchange(&g_armed, 0);
}

__declspec(dllexport) void bltrace_enter(void *retaddr)
{
  if (g_armed == 0) {
    return;
  }
  if (g_base == 0) {
    return;
  }
  uint64_t rva = (uint64_t)(uintptr_t)retaddr - g_base;
  if (rva == 0) {
    return;
  }

  LARGE_INTEGER tick;
  QueryPerformanceCounter(&tick);
  uint64_t t0 = (uint64_t)tick.QuadPart;

  TlsStack *state = tls_state();
  uint64_t caller = 0;
  if (state != NULL && state->count > 0) {
    caller = state->stack[state->count - 1].rva;
  }

  uint64_t edge = (caller << 32) | (uint32_t)rva;
  if (edge != 0) {
    if (claim(g_eslots, SLOT_MASK, edge)) {
      _InterlockedIncrement(&g_ecount);
    }
  }
  if (claim(g_slots, SLOT_MASK, rva + 1)) {
    _InterlockedIncrement(&g_count);
  }

  if (state != NULL) {
    if (state->count >= STACK_CAP) {
      state->count = 0;
    }
    else {
      TlsFrame *frame = &state->stack[state->count];
      frame->rva = rva;
      frame->t0 = t0;
      frame->child = 0;
      state->count++;
    }
  }
}

__declspec(dllexport) void bltrace_exit(void *retaddr)
{
  (void)retaddr;
  if (g_armed == 0) {
    return;
  }
  if (g_tls == TLS_OUT_OF_INDEXES) {
    return;
  }
  TlsStack *state = (TlsStack *)TlsGetValue(g_tls);
  if (state == NULL || state->count <= 0) {
    return;
  }

  int top = state->count - 1;
  TlsFrame frame = state->stack[top];
  state->count = top;

  LARGE_INTEGER tick;
  QueryPerformanceCounter(&tick);
  uint64_t now = (uint64_t)tick.QuadPart;
  uint64_t inclusive = now >= frame.t0 ? now - frame.t0 : 0;
  uint64_t self = inclusive >= frame.child ? inclusive - frame.child : 0;

  if (g_tslots != NULL) {
    TimingSlot *slot = timing_slot(frame.rva + 1);
    if (slot != NULL) {
      _InterlockedIncrement64((volatile __int64 *)&slot->count);
      _InterlockedExchangeAdd64((volatile __int64 *)&slot->self, (__int64)self);
      _InterlockedExchangeAdd64(
          (volatile __int64 *)&slot->inclusive, (__int64)inclusive);
    }
  }

  if (top > 0) {
    state->stack[top - 1].child += inclusive;
    if (g_rslots != NULL) {
      uint64_t callee = frame.rva;
      uint64_t caller = state->stack[top - 1].rva;
      uint64_t edge = (callee << 32) | (uint32_t)caller;
      if (edge != 0 && claim(g_rslots, SLOT_MASK, edge)) {
        _InterlockedIncrement(&g_rcount);
      }
    }
  }
}

__declspec(dllexport) void bltrace_reset(void)
{
  if (g_slots != NULL) {
    __stosq((unsigned __int64 *)g_slots, 0, SLOT_COUNT);
  }
  if (g_eslots != NULL) {
    __stosq((unsigned __int64 *)g_eslots, 0, SLOT_COUNT);
  }
  if (g_rslots != NULL) {
    __stosq((unsigned __int64 *)g_rslots, 0, SLOT_COUNT);
  }
  if (g_tslots != NULL) {
    __stosq((unsigned __int64 *)g_tslots, 0,
            (size_t)TIME_SLOT_COUNT * sizeof(TimingSlot) / sizeof(uint64_t));
  }
  _InterlockedExchange(&g_tcount, 0);
  if (g_tls != TLS_OUT_OF_INDEXES) {
    TlsStack *state = tls_state();
    if (state != NULL) {
      state->count = 0;
    }
  }
  _InterlockedExchange(&g_count, 0);
  _InterlockedExchange(&g_ecount, 0);
  _InterlockedExchange(&g_rcount, 0);
}

__declspec(dllexport) void bltrace_dump(const char *path)
{
  uint64_t *table = g_slots;
  if (table == NULL) {
    return;
  }
  HANDLE file = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                            CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
  if (file == INVALID_HANDLE_VALUE) {
    return;
  }
  DWORD written = 0;
  for (uint32_t i = 0; i < SLOT_COUNT; i++) {
    uint64_t value = table[i];
    if (value != 0) {
      WriteFile(file, &value, sizeof(value), &written, NULL);
    }
  }
  CloseHandle(file);
}

__declspec(dllexport) void bltrace_dump_edges(const char *path)
{
  uint64_t *table = g_eslots;
  if (table == NULL) {
    return;
  }
  HANDLE file = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                            CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
  if (file == INVALID_HANDLE_VALUE) {
    return;
  }
  DWORD written = 0;
  for (uint32_t i = 0; i < SLOT_COUNT; i++) {
    uint64_t value = table[i];
    if (value != 0) {
      WriteFile(file, &value, sizeof(value), &written, NULL);
    }
  }
  CloseHandle(file);
}

__declspec(dllexport) void bltrace_dump_returns(const char *path)
{
  uint64_t *table = g_rslots;
  if (table == NULL) {
    return;
  }
  HANDLE file = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                            CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
  if (file == INVALID_HANDLE_VALUE) {
    return;
  }
  DWORD written = 0;
  for (uint32_t i = 0; i < SLOT_COUNT; i++) {
    uint64_t value = table[i];
    if (value != 0) {
      WriteFile(file, &value, sizeof(value), &written, NULL);
    }
  }
  CloseHandle(file);
}

__declspec(dllexport) uint32_t bltrace_timing_count(void)
{
  return (uint32_t)g_tcount;
}

__declspec(dllexport) void bltrace_dump_timings(const char *path)
{
  TimingSlot *table = g_tslots;
  if (table == NULL) {
    return;
  }
  HANDLE file = CreateFileA(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                            CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
  if (file == INVALID_HANDLE_VALUE) {
    return;
  }

  TimingHeader header;
  header.magic = TIME_MAGIC;
  header.version = TIME_VERSION;
  header.freq = g_qpc_freq;
  header.record_size = (uint32_t)sizeof(TimingRecord);
  header.count = (uint32_t)g_tcount;

  DWORD written = 0;
  WriteFile(file, &header, sizeof(header), &written, NULL);
  for (uint32_t i = 0; i < TIME_SLOT_COUNT; i++) {
    TimingSlot *slot = &table[i];
    if (slot->key == 0) {
      continue;
    }
    TimingRecord record;
    record.key = slot->key;
    record.count = slot->count;
    record.self = slot->self;
    record.inclusive = slot->inclusive;
    WriteFile(file, &record, sizeof(record), &written, NULL);
  }
  CloseHandle(file);
}

__declspec(dllexport) uint32_t bltrace_edge_count(void)
{
  return (uint32_t)g_ecount;
}

__declspec(dllexport) uint32_t bltrace_return_count(void)
{
  return (uint32_t)g_rcount;
}