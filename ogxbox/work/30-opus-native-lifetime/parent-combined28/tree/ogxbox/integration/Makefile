# ogxbox/integration -- host tests (gcc/clang/asan) + XBE install-plan check.
#
#   make test           gcc host test (real core/gip.c -> og_gip -> ogx_present)
#   make test-clang     clang
#   make asan           gcc -fsanitize=address,undefined
#   make verify         detour_plan.py against the pinned XBE (--xbe supported)
#   make pic            i386 static-PIE build + relocation audit (R_386_RELATIVE only)
#   make clean

CC      ?= cc
CFLAGS  ?= -O2 -g -Wall -Wextra -Wno-unused-parameter
ASAN     = -fsanitize=address,undefined -fno-omit-frame-pointer

ECC_FLAGS = -DuECC_SUPPORTS_secp160r1=0 -DuECC_SUPPORTS_secp192r1=0 \
	-DuECC_SUPPORTS_secp224r1=0 -DuECC_SUPPORTS_secp256k1=0 -DuECC_PLATFORM=uECC_arch_other

UP     = ../..
CORE   = $(UP)/core/mt76.c $(UP)/core/dongle.c $(UP)/core/gip.c $(UP)/core/sha256.c

# production presentation + adapter + host platform
PRESENT = ogx_present.c ../halo2/xinput_model.c
ADAPTER = ../gip/og_gip.c ../gip/og_host_platform.c
TEST    = $(ADAPTER) $(PRESENT) test_integration.c

INCS    = -I$(UP) -I$(UP)/core -I.. -I../gip -I../halo2 -I.

test: $(TEST) uECC.o
	$(CC) $(CFLAGS) $(INCS) -o $@ $(TEST) $(CORE) uECC.o

test-clang: $(TEST) uECC.o
	clang $(CFLAGS) $(INCS) -o $@ $(TEST) $(CORE) uECC.o

asan: $(TEST) uECC_asan.o
	$(CC) $(CFLAGS) $(ASAN) $(INCS) -o $@ $(TEST) $(CORE) uECC_asan.o

uECC.o: $(UP)/third_party/micro-ecc/uECC.c
	$(CC) -O2 $(ECC_FLAGS) -I$(UP) -c -o $@ $<

uECC_asan.o: $(UP)/third_party/micro-ecc/uECC.c
	$(CC) -O1 -g $(ECC_FLAGS) $(ASAN) -I$(UP) -c -o $@ $<

verify:
	python3 detour_plan.py

pic:
	bash build_pic.sh

clean:
	rm -f test test-clang asan uECC.o uECC_asan.o
	rm -rf out

.PHONY: clean verify pic
