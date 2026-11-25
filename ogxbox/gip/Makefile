# og_gip: wired Xbox One -> OG Xbox input adapter, host build.
# Links the REAL core/gip.c parser (plus the wireless core it shares) against the
# adapter and its tests. No external packages; libc + a C11 compiler suffice.
#
#   make test            gcc, debug + warnings
#   make CC=clang test   clang
#   make asan            gcc, -fsanitize=address,undefined
#   make hardtest        gcc, the hardening/boundary regression suite
#   make hardtest_asan   gcc, hardening suite under ASan/UBSan
#   make clean

CC     ?= cc
CFLAGS ?= -O2 -g -Wall -Wextra -Wno-unused-parameter
ASAN    = -fsanitize=address,undefined -fno-omit-frame-pointer

# micro-ecc: only P-256, portable C (same as desktop/Makefile)
ECC_FLAGS = -DuECC_SUPPORTS_secp160r1=0 -DuECC_SUPPORTS_secp192r1=0 \
	-DuECC_SUPPORTS_secp224r1=0 -DuECC_SUPPORTS_secp256k1=0 -DuECC_PLATFORM=uECC_arch_other

UP     = ../..
CORE   = $(UP)/core/mt76.c $(UP)/core/dongle.c $(UP)/core/gip.c $(UP)/core/sha256.c
ADAPTER = og_gip.c og_host_platform.c
TEST    = $(ADAPTER) og_gip_test.c
HARD    = $(ADAPTER) og_gip_hardening_test.c
HEADERS = og_gip.h og_gamepad.h og_host_platform.h

test: $(TEST) $(HEADERS) $(CORE) uECC.o
	$(CC) $(CFLAGS) -I$(UP) -I$(UP)/core -o $@ $(TEST) $(CORE) uECC.o

hardtest: $(HARD) $(HEADERS) $(CORE) uECC.o
	$(CC) $(CFLAGS) -I$(UP) -I$(UP)/core -o $@ $(HARD) $(CORE) uECC.o

asan: $(TEST) $(HEADERS) $(CORE) uECC_asan.o
	$(CC) $(CFLAGS) $(ASAN) -I$(UP) -I$(UP)/core -o $@ $(TEST) $(CORE) uECC_asan.o

hardtest_asan: $(HARD) $(HEADERS) $(CORE) uECC_asan.o
	$(CC) $(CFLAGS) $(ASAN) -I$(UP) -I$(UP)/core -o $@ $(HARD) $(CORE) uECC_asan.o

uECC.o: $(UP)/third_party/micro-ecc/uECC.c
	$(CC) -O2 $(ECC_FLAGS) -I$(UP) -c -o $@ $<

uECC_asan.o: $(UP)/third_party/micro-ecc/uECC.c
	$(CC) -O1 -g $(ECC_FLAGS) $(ASAN) -I$(UP) -c -o $@ $<

clean:
	rm -f test hardtest asan hardtest_asan uECC.o uECC_asan.o

.PHONY: clean
