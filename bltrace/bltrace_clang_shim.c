/*
 * bltrace_clang_shim.c -- clang -finstrument-functions entry points.
 *
 * Reuses bltrace_hook.c: this_fn is the function entry address, which is
 * exactly what bltrace_enter() expects (it subtracts the module base).
 * The matching exit hook pops the TLS stack, so call/return edges keep the
 * same function-entry semantics as the MSVC /Gh build.
 *
 * This translation unit is compiled with -fno-instrument-functions* to
 * avoid hook recursion.
 */

void bltrace_enter(void *addr);
void bltrace_exit(void *addr);

__declspec(noinline) void __cyg_profile_func_enter(void *this_fn, void *call_site)
{
  (void)call_site;
  bltrace_enter(this_fn);
}

__declspec(noinline) void __cyg_profile_func_exit(void *this_fn, void *call_site)
{
  (void)this_fn;
  (void)call_site;
  bltrace_exit(0);
}
