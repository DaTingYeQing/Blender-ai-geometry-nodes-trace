/*
 * covtrace_hook.c -- coverage window control.
 *
 * Called from the run script through GetProcAddress:
 *   covtrace_arm(path)   point profraw output at path and reset counters
 *   covtrace_dump(path)  write the current window, then redirect exit output
 *
 * The three runtime functions are linked in by -fprofile-instr-generate.
 */

#include <stdint.h>

extern void __llvm_profile_set_filename(const char *filename);
extern void __llvm_profile_reset_counters(void);
extern int __llvm_profile_write_file(void);

/* bltrace.lib's /EXPORT directives are dropped by the blender link, so expose
 * its API through this directly-linked object instead. */
extern int bltrace_arm(void);
extern void bltrace_reset(void);
extern void bltrace_dump(const char *path);
extern void bltrace_dump_edges(const char *path);
extern void bltrace_dump_timings(const char *path);
extern uint32_t bltrace_edge_count(void);
extern uint32_t bltrace_timing_count(void);
extern int bltrace_disarm(void);

__declspec(dllexport) int covtrace_calls_arm(void)
{
  /* bltrace_arm() returns the previous armed state, not success. */
  bltrace_arm();
  return 1;
}

__declspec(dllexport) void covtrace_calls_reset(void)
{
  bltrace_reset();
}

__declspec(dllexport) void covtrace_calls_dump(const char *path)
{
  bltrace_dump(path);
}

__declspec(dllexport) void covtrace_calls_dump_edges(const char *path)
{
  bltrace_dump_edges(path);
}

__declspec(dllexport) void covtrace_calls_dump_timings(const char *path)
{
  bltrace_dump_timings(path);
}

__declspec(dllexport) uint32_t covtrace_calls_edge_count(void)
{
  return bltrace_edge_count();
}

__declspec(dllexport) uint32_t covtrace_calls_timing_count(void)
{
  return bltrace_timing_count();
}

__declspec(dllexport) int covtrace_calls_disarm(void)
{
  return bltrace_disarm();
}

__declspec(dllexport) void covtrace_arm(const char *filename)
{
  __llvm_profile_set_filename(filename);
  __llvm_profile_reset_counters();
}

__declspec(dllexport) int covtrace_dump(const char *filename)
{
  /* Write the window file first, then redirect the atexit write (normally to
   * NUL) so it cannot overwrite the window data. */
  int rc = __llvm_profile_write_file();
  if (filename && filename[0] != '\0') {
    __llvm_profile_set_filename(filename);
  }
  return rc;
}
