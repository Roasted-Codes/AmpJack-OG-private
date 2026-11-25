/* Host runtime test of the E9 detour + stdcall mechanism on real i386.
 *
 * NOT a USB or hardware test. It proves the 5-byte `E9 rel32` detour primitive,
 * the stdcall argument passing, and the "serve virtual path vs chain to original"
 * dispatch execute correctly on the same ISA (i386) the Xbox title uses.
 * The clone-of-original technique here stands in for the loader's relocated
 * displaced bytes (whose exact bytes are verified statically by verify_hooks.py).
 * Synthetic fixture only.
 *
 * Build:  gcc -m32 -o test_hook test_hook.c ; ./test_hook
 */
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static volatile uint8_t g_enable = 0;   /* disabled-by-default contract */
static int32_t g_fake_state = 777;

/* Function pointer to the unpatched clone of target (the "original"). */
static int (*g_orig)(int, int *);

/* The "original" XInputGetState stand-in (stdcall), synthetic. */
__attribute__((noinline, stdcall))
int target_getstate(int handle, int *pstate)
{
    *pstate = g_fake_state;             /* pretend to read the device */
    return handle * 2;                  /* deterministic original result */
}

/* The trampoline (stand-in for ampjack_stub_getstate). */
__attribute__((noinline, stdcall))
int detour_getstate(int handle, int *pstate)
{
    if (g_enable) {
        *pstate = 424242;               /* virtual path: adapter-mapped state */
        return 0;                       /* XINPUT_ERR_SUCCESS */
    }
    return g_orig(handle, pstate);      /* chain path: run original */
}

static void patch_e9(void *site, void *target)
{
    uint8_t *b = (uint8_t *)site;
    intptr_t rel = (intptr_t)target - ((intptr_t)site + 5);
    b[0] = 0xE9;
    memcpy(b + 1, &rel, 4);
}

/* Clone a function's bytes into a fresh RWX page, return a callable pointer. */
static void *clone_fn(const void *src, size_t len)
{
    void *p = mmap(NULL, len, PROT_READ | PROT_WRITE | PROT_EXEC,
                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (p == MAP_FAILED) { perror("mmap"); return NULL; }
    memcpy(p, src, len);
    __builtin___clear_cache((char *)p, (char *)p + len);
    return p;
}

int main(void)
{
    long page = sysconf(_SC_PAGESIZE);

    /* Clone the original before patching. */
    g_orig = (int (*)(int, int *))clone_fn((void *)target_getstate, 64);
    if (!g_orig) return 2;

    /* Make target's page writable and apply the 5-byte E9 detour. */
    void *base = (void *)((uintptr_t)target_getstate & ~(uintptr_t)(page - 1));
    mprotect(base, (size_t)page, PROT_READ | PROT_WRITE | PROT_EXEC);
    uint8_t saved[5];
    memcpy(saved, target_getstate, 5);
    patch_e9(target_getstate, detour_getstate);
    __builtin___clear_cache((char *)target_getstate, (char *)target_getstate + 16);

    int state = 0; int failed = 0;

    /* Disabled -> chain to original. */
    g_enable = 0;
    int r1 = target_getstate(21, &state);
    if (r1 == 42 && state == 777) {
        printf("ok:   disabled chains to original (r=%d state=%d)\n", r1, state);
    } else { printf("FAIL: disabled chain r=%d state=%d\n", r1, state); failed++; }

    /* Enabled -> virtual path. */
    g_enable = 1;
    int r2 = target_getstate(21, &state);
    if (r2 == 0 && state == 424242) {
        printf("ok:   enabled serves virtual path (r=%d state=%d)\n", r2, state);
    } else { printf("FAIL: enabled virtual r=%d state=%d\n", r2, state); failed++; }

    /* Restore original bytes. */
    memcpy(target_getstate, saved, 5);
    __builtin___clear_cache((char *)target_getstate, (char *)target_getstate + 16);

    printf("\n%s: %d failure(s)\n", failed == 0 ? "PASS" : "FAIL", failed);
    return failed == 0 ? 0 : 1;
}
