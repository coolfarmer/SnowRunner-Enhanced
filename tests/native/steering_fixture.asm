; Test fixture derived from SnowRunner FFB Fix (MIT).
EXTERN FixtureBody:PROC
EXTERN abi_snapshot:BYTE
.code
FixtureCtor PROC
    mov [rsp+16], rdx
    mov [rsp+8], rcx
    jmp FixtureBody
    REPT 32
    nop
    ENDM
FixtureCtor ENDP
AbiTarget PROC
    mov [rsp+16], rdx
    mov [rsp+8], rcx
    mov QWORD PTR [abi_snapshot+0], rax
    mov QWORD PTR [abi_snapshot+8], rcx
    mov QWORD PTR [abi_snapshot+16], rdx
    mov QWORD PTR [abi_snapshot+24], r8
    mov QWORD PTR [abi_snapshot+32], r9
    mov QWORD PTR [abi_snapshot+40], r10
    mov QWORD PTR [abi_snapshot+48], r11
    pushfq
    pop rax
    mov QWORD PTR [abi_snapshot+56], rax
    movdqu XMMWORD PTR [abi_snapshot+64], xmm0
    movdqu XMMWORD PTR [abi_snapshot+80], xmm1
    movdqu XMMWORD PTR [abi_snapshot+96], xmm2
    movdqu XMMWORD PTR [abi_snapshot+112], xmm3
    movdqu XMMWORD PTR [abi_snapshot+128], xmm4
    movdqu XMMWORD PTR [abi_snapshot+144], xmm5
    mov rax, [rsp+40]
    mov QWORD PTR [abi_snapshot+160], rax
    mov rax, [rsp+48]
    mov QWORD PTR [abi_snapshot+168], rax
    mov rax, 12345
    ret
AbiTarget ENDP
AbiInvoke PROC FRAME
    sub rsp, 56
    .allocstack 56
    .endprolog
    mov QWORD PTR [rsp+32], 111
    mov QWORD PTR [rsp+40], 222
    mov rax, 123
    mov rdx, 234
    mov r8, 345
    mov r9, 456
    mov r10, 567
    mov r11, 678
    pcmpeqb xmm0, xmm0
    movdqa xmm1, xmm0
    psrlq xmm1, 1
    movdqa xmm2, xmm1
    psrlq xmm2, 1
    movdqa xmm3, xmm2
    psrlq xmm3, 1
    movdqa xmm4, xmm3
    psrlq xmm4, 1
    movdqa xmm5, xmm4
    psrlq xmm5, 1
    cmp rax, rax
    stc
    call AbiTarget
    add rsp, 56
    ret
AbiInvoke ENDP
END
