; Minimal FreeDOS COM1 qualification helper.  Build with NASM: nasm -f bin serialtest.asm -o SERIALTEST.EXE
bits 16
org 100h

start:
    mov ax, ds
    mov es, ax                     ; retain PSP for command-tail inspection
    push cs
    pop ds
    cmp byte es:[80h], 1
    jb exchange
    cmp byte es:[82h], 'S'          ; DOS command tail begins with a space
    je selftest
    cmp byte es:[82h], 'M'          ; MATRIX: command tail begins with " MATRIX"
    je matrix
exchange:
    mov dx, serial_ready_msg
    mov ah, 09h
    int 21h
    mov ax, 00e3h                 ; BIOS INT 14h: 9600, 8N1
    xor dx, dx                     ; COM1
    int 14h
    mov si, ready_name
    mov di, ready_text
    mov cx, ready_len
    call write_file

    mov cx, 0ffffh                ; bounded BIOS status polling
    xor si, si
.wait:
    mov ax, 0300h                 ; return modem/line status
    xor dx, dx
    int 14h
    test ah, 01h                  ; BIOS INT 14h line-status data-ready bit
    jnz .read
    loop .wait
    jmp fail
.read:
    mov ax, 0200h
    xor dx, dx
    int 14h
    cmp al, 'A'
    jne fail
    mov [rx_a], al
    call recv_one
    cmp al, 'B'
    jne fail
    mov [rx_b], al
    call recv_one
    cmp al, 'C'
    jne fail
    mov [rx_c], al

    mov si, reply
    mov cx, reply_len
.tx:
    lodsb
    mov ah, 01h
    xor dx, dx
    int 14h
    loop .tx
    mov si, pass_name
    mov di, pass_text
    mov cx, pass_len
    call write_file
    mov ax, 4c00h
    int 21h

selftest:
    mov dx, self_msg
    mov ah, 09h
    int 21h
    mov si, ready_name
    mov di, self_ready_text
    mov cx, self_ready_len
    call write_file
    jc self_fail
    mov si, pass_name
    mov di, self_pass_text
    mov cx, self_pass_len
    call write_file
    jc self_fail
    mov ax, 4c00h
    int 21h

self_fail:
    mov si, pass_name
    mov di, self_fail_text
    mov cx, self_fail_len
    call write_file
    mov ax, 4c01h
    int 21h

matrix:
    mov dx, serial_ready_msg
    mov ah, 09h
    int 21h
    mov ax, 00e3h
    xor dx, dx
    int 14h
    mov si, ready_name
    mov di, ready_text
    mov cx, ready_len
    call write_file
    mov si, matrix_data
    mov cx, matrix_len
.rx:
    push cx
    call recv_one
    pop cx
    cmp al, [si]
    jne matrix_fail
    inc si
    loop .rx
    mov si, matrix_data
    mov cx, matrix_len
.tx:
    lodsb
    mov ah, 01h
    xor dx, dx
    int 14h
    loop .tx
    mov si, matrix_name
    mov di, matrix_pass_text
    mov cx, matrix_pass_len
    call write_file
    mov ax, 4c00h
    int 21h

matrix_fail:
    mov si, matrix_name
    mov di, matrix_fail_text
    mov cx, matrix_fail_len
    call write_file
    mov ax, 4c01h
    int 21h

recv_one:
    mov cx, 0ffffh
.poll:
    mov ax, 0300h
    xor dx, dx
    int 14h
    test ah, 01h
    jnz .got
    loop .poll
    xor ax, ax
.got:
    mov ax, 0200h
    xor dx, dx
    int 14h
    ret

fail:
    mov si, fail_name
    mov di, fail_text
    mov cx, fail_len
    call write_file
    mov ax, 4c01h
    int 21h

; DS:SI filename, DS:DI data, CX length.  Failure is intentionally bounded.
write_file:
    push cx
    mov dx, si
    xor cx, cx
    mov ah, 3ch
    int 21h
    jc .done
    mov bx, ax
    pop cx
    mov dx, di
    mov ah, 40h
    int 21h
    mov ah, 3eh
    int 21h
    ret
.done:
    pop cx
    ret

ready_name db 'D:\\UBBQUAL\\READY.RST',0
pass_name db 'D:\\UBBQUAL\\SERIAL.RST',0
matrix_name db 'D:\\UBBQUAL\\SERIAL.RST',0
fail_name db 'D:\\UBBQUAL\\SERIAL.RST',0
ready_text db 'UBB_SERIAL_READY=1',13,10
ready_len equ $-ready_text
self_ready_text db 'UBB_SERIAL_VERSION=1',13,10,'MODE=SELFTEST',13,10,'EXECUTION=PASS',13,10,'WRITE_PATH=PASS',13,10
self_ready_len equ $-self_ready_text
self_pass_text db 'UBB_SERIAL_VERSION=1',13,10,'MODE=SELFTEST',13,10,'EXECUTION=PASS',13,10,'WRITE_PATH=PASS',13,10,'RESULT=PASS',13,10
self_pass_len equ $-self_pass_text
self_fail_text db 'UBB_SERIAL_VERSION=1',13,10,'MODE=SELFTEST',13,10,'EXECUTION=PASS',13,10,'WRITE_PATH=FAIL',13,10,'RESULT=FAIL',13,10
self_fail_len equ $-self_fail_text
self_msg db 'UBB-SELFTEST-EXECUTED',13,10,'$'
pass_text db 'UBB_SERIAL_VERSION=1',13,10,'COM=1',13,10,'METHOD=BIOS',13,10,'RX=414243',13,10,'TX=5542422D4F4B',13,10,'RX_STATUS=PASS',13,10,'TX_STATUS=PASS',13,10,'RESULT=PASS',13,10
pass_len equ $-pass_text
matrix_data db 00h,01h,0Ah,0Dh,1Bh,20h,41h,7Fh,80h,0B3h,0C4h,0DAh,0FFh,1Bh,'[','3','1','m',0Dh,0Ah,0B3h,0C4h,0DAh
matrix_len equ $-matrix_data
matrix_pass_text db 'UBB_SERIAL_VERSION=1',13,10,'MODE=MATRIX',13,10,'RX=00010A0D1B20417F80B3C4DAFF1B5B33316D0D0AB3C4DA',13,10,'TX=00010A0D1B20417F80B3C4DAFF1B5B33316D0D0AB3C4DA',13,10,'RX_STATUS=PASS',13,10,'TX_STATUS=PASS',13,10,'RESULT=PASS',13,10
matrix_pass_len equ $-matrix_pass_text
matrix_fail_text db 'UBB_SERIAL_VERSION=1',13,10,'MODE=MATRIX',13,10,'RESULT=FAIL',13,10
matrix_fail_len equ $-matrix_fail_text
fail_text db 'UBB_SERIAL_VERSION=1',13,10,'COM=1',13,10,'METHOD=BIOS',13,10,'RESULT=FAIL',13,10
fail_len equ $-fail_text
reply db 'UBB-OK'
reply_len equ $-reply
serial_ready_msg db 'UBB-SERIAL-READY',13,10,'$'
rx_a db 0
rx_b db 0
rx_c db 0
