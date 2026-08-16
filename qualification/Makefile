.PHONY: all clean
all: SERIALTEST.EXE

SERIALTEST.EXE: serialtest.asm
	nasm -f bin $< -o $@

clean:
	rm -f SERIALTEST.EXE
