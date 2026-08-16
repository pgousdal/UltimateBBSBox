; Minimal FreeDOS COM1 qualification helper.  Build with NASM: nasm -f bin serialtest.asm -o SERIALTEST.EXE
bits 16
org 100h

start:
    push cs
    pop ds
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
    test al, 01h                  ; line-status data-ready bit
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

recv_one:
    mov cx, 0ffffh
.poll:
    mov ax, 0300h
    xor dx, dx
    int 14h
    test al, 01h
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

ready_name db 'C:\\UBBQUAL\\READY.RST',0
pass_name db 'C:\\UBBQUAL\\SERIAL.RST',0
fail_name db 'C:\\UBBQUAL\\SERIAL.RST',0
ready_text db 'UBB_SERIAL_READY=1',13,10
ready_len equ $-ready_text
pass_text db 'UBB_SERIAL_VERSION=1',13,10,'COM=1',13,10,'METHOD=BIOS',13,10,'RX=414243',13,10,'TX=5542422D4F4B',13,10,'RX_STATUS=PASS',13,10,'TX_STATUS=PASS',13,10,'RESULT=PASS',13,10
pass_len equ $-pass_text
fail_text db 'UBB_SERIAL_VERSION=1',13,10,'COM=1',13,10,'METHOD=BIOS',13,10,'RESULT=FAIL',13,10
fail_len equ $-fail_text
reply db 'UBB-OK'
reply_len equ $-reply
rx_a db 0
rx_b db 0
rx_c db 0
