'use strict';

// Experimental VM filter. Resources are pinned until process exit because
// a direct replacement does not track in-flight calls for safe dynamic freeing.
const fastMenuResources = [];
// Generate bounded, exact name matching. Each branch reads one byte, so short
// strings at a page boundary are safe. Both VM string terminators are accepted.
function fastVmNameTrie(names) {
    const root={children:new Map(),mask:0};
    names.forEach((name,index)=>{
        let node=root;
        for(const char of name) {
            const code=char.charCodeAt(0);
            if(!node.children.has(code))node.children.set(code,{children:new Map(),mask:0});
            node=node.children.get(code);
        }
        node.mask=(node.mask | (2**index))>>>0;
    });
    const emit=node=>`switch(*p++){${node.mask?'case 0:case 255:return '+node.mask+'U;':''}${
        [...node.children].map(([code,child])=>'case '+code+':'+emit(child)).join('')}default:return 0;}`;
    return emit(root);
}
function makeFastMenuHooks(expectedEntry, hostModule = Process.getModuleByName('SnowRunnerEnhanced.asi')) {
    if (Process.arch !== 'x64' || Process.platform !== 'windows') throw Error('Fast menu requires Windows x64');
    const entries = [];
    const atInterior = expectedEntry.interior === true;
    const split = expectedEntry.splitOffset === 8;
    const indexed = expectedEntry.indexed ?? (typeof ENHANCED_VM_INDEXED!=='undefined' && ENHANCED_VM_INDEXED);
    const prefixes = indexed && (expectedEntry.prefixes ??
        (typeof ENHANCED_VM_PREFIXES !== 'undefined' && ENHANCED_VM_PREFIXES));
    if(split && (!atInterior || !expectedEntry.hex.startsWith('488b4950488b4118')))
        throw Error('Unsupported split VM observer');
    let frame = null, pool = null, group = null, sealed = false;
    function attach(framePush, poolSlot, update, targetClass, targetMethod, interior = false, phase = 0) {
        if (sealed || interior !== atInterior || entries.length >= 32 || typeof update !== 'function' ||
                (phase !== 0 && !(split && phase === 1)) ||
                !/^[A-Za-z_][A-Za-z_0-9]*$/.test(targetClass) ||
                !/^[A-Za-z_][A-Za-z_0-9]*$/.test(targetMethod)) throw Error('Invalid fast menu registration');
        if (!framePush.equals(expectedEntry.address) ||
                (frame && (!frame.equals(framePush) || !pool.equals(poolSlot)))) throw Error('Fast menu entry/pool mismatch');
        frame = framePush; pool = poolSlot;
        const item = {update, targetClass, targetMethod, phase, index: entries.length, active: true};
        entries.push(item);
        return {detach() {
            if (!item.active) return;
            item.active = false;
            if (group) {
                group.state.add(16 + 16 * item.index + 8).writeU64(0);
                if (!entries.some(entry => entry.active)) group.state.add(8).writeU64(0);
            }
        }};
    }
    attach.commit = () => {
        if (sealed) throw Error('Fast menu already committed');
        sealed = true;
        if (!entries.length || !entries.some(entry => entry.active)) return;
        const expected = Uint8Array.from(expectedEntry.hex.match(/../g).map(value => parseInt(value,16)));
        const current = new Uint8Array(frame.readByteArray(expected.length));
        if (!expected.length || !current.every((value,i)=>value===expected[i])) throw Error('Fast menu entry changed');
        const originalBytes = Memory.alloc(expected.length); originalBytes.writeByteArray(expected);
        const indexOffset=16+16*entries.length;
        const state = Memory.alloc(indexOffset + (indexed?528:0));
        state.writePointer(pool); state.add(8).writeU64(1);
        entries.forEach((item,i) => {
            state.add(16+16*i).writePointer(ptr(0));
            state.add(24+16*i).writeU64(item.active?1:0);
        });
        if(indexed) {
            for(let phase=0;phase<2;phase++) {
                const mask=entries.reduce((mask,item,i)=>item.active&&item.phase===phase?(mask|(2**i))>>>0:mask,0);
                state.add(indexOffset+512+4*phase).writeU32(mask);
            }
        }
        const callbacks = entries.map(item=>new NativeCallback(item.update,'void',['pointer','pointer']));
        const kernel = Process.getModuleByName('kernel32.dll');
        const symbols = {state, get_error:kernel.getExportByName('GetLastError'), set_error:kernel.getExportByName('SetLastError'),
            thread_state:hostModule.getExportByName('EnhancedFastMenuThreadState')};
        if(indexed) {
            symbols.remember_target=hostModule.getExportByName('EnhancedRememberVmTarget');
            symbols.resolve_registration=hostModule.getExportByName('EnhancedResolveVmRegistration');
        }
        callbacks.forEach((cb,i)=>{symbols['update'+i]=cb;});
        const module = new CModule(`
#include <stdint.h>
typedef struct { uint64_t target, active; } Entry;
typedef struct { uint64_t pool_slot, enabled; Entry entries[${entries.length}];
${indexed?'volatile uint64_t known[64]; volatile uint32_t unresolved[2]; volatile uint64_t overflow;':''}
} State;
extern State state;
extern unsigned get_error(void);
extern void set_error(unsigned value);
extern unsigned *thread_state(void);
${entries.map((_,i)=>'extern void update'+i+'(void *, void *);').join('\n')}
typedef void (*Update)(void *, void *);
static const struct { const char *cls, *method; Update update; unsigned phase; } entries[] = {
${entries.map((item,i)=>`{${JSON.stringify(item.targetClass)},${JSON.stringify(item.targetMethod)},update${i},${item.phase}}`).join(',\n')}
};
static uint64_t word(uint64_t p) { return *(uint64_t *)(uintptr_t)p; }
${indexed?`
extern int remember_target(volatile uint64_t *table, void *target);
extern void resolve_registration(volatile uint32_t *mask, uint32_t bit);
static uint32_t class_mask(const unsigned char *p) { ${fastVmNameTrie(entries.map(item=>item.targetClass))} }
static uint32_t method_mask(const unsigned char *p) { ${fastVmNameTrie(entries.map(item=>item.targetMethod))} }
static int might_match(uint64_t fn,unsigned phase) {
    unsigned bucket=(unsigned)((fn>>4)^(fn>>13))&63,i;
    uint64_t cls,signature,pool;
    uint32_t id,mask;
    if(state.overflow)return 1;
    for(i=0;i<64;i++) {
        uint64_t known=state.known[(bucket+i)&63];
        if(known==fn)return 1;
        if(!known)break;
    }
    if(i==64)return 1;
    mask=state.unresolved[phase];if(!mask)return 0;
    cls=word(fn+0x48);if(!cls)return 0;
    id=*(uint32_t *)(uintptr_t)(cls+0x18);if(id>0x10000000)return 0;
    pool=word(state.pool_slot);
    mask &= class_mask((const unsigned char *)(uintptr_t)(pool+id));if(!mask)return 0;
    signature=word(fn+0x40);if(!signature)return 0;
    id=*(uint32_t *)(uintptr_t)signature;if(id>0x10000000)return 0;
    return (mask & method_mask((const unsigned char *)(uintptr_t)(pool+id)))!=0;
}
`:''}
static int named(uint32_t id, const char *expected) {
    const unsigned char *p;
    if (id > 0x10000000) return 0;
    p = (const unsigned char *)(uintptr_t)(word(state.pool_slot)+id);
    while (*expected) if (*p++ != (unsigned char)*expected++) return 0;
    return *p==0 || *p==255;
}
static void dispatch_phase(void *vm, void *method, unsigned phase) {
    uint64_t fn=(uint64_t)(uintptr_t)method;
    unsigned i;
    unsigned *depth;
    if (!state.enabled) return;
    depth=thread_state();
    if (*depth) return;
    ${indexed?'if(!might_match(fn,phase))return;':''}
    for (i=0;i<${entries.length};++i) {
        uint64_t cls, signature;
        unsigned error;
        if (!state.entries[i].active || entries[i].phase!=phase) continue;
        if (state.entries[i].target) {
            if (fn!=state.entries[i].target) continue;
        } else {
            cls=word(fn+0x48); if (!cls) continue;
            if (!named(*(uint32_t *)(uintptr_t)(cls+0x18),entries[i].cls)) continue;
            signature=word(fn+0x40); if (!signature) continue;
            if (!named(*(uint32_t *)(uintptr_t)signature,entries[i].method)) continue;
            ${indexed?'if(!remember_target(state.known,method))state.overflow=1;':''}
            state.entries[i].target=fn;
            ${indexed?'resolve_registration(&state.unresolved[phase],1U<<i);':''}
        }
        error=get_error();
        /* Match Interceptor's suppression of calls made from its callbacks. */
        *depth=1;
        entries[i].update(vm,method);
        *depth=0;
        set_error(error);
    }
}
void dispatch(void *vm, void *method) { dispatch_phase(vm,method,0); }
void dispatch_after(void *vm, void *method) { dispatch_phase(vm,method,1); }
`,symbols);
        // Preserve the full Windows x64 volatile register set, flags and SSE
        // arguments, then tail-jump to the relocated original with its stack
        // and return address intact. No guessed original function prototype.
        const gate = Memory.alloc(Process.pageSize * 2);
        const originalSlot = gate.add(Process.pageSize); originalSlot.writePointer(ptr(0));
        const w = new X86Writer(gate,{pc:gate});
        const registers=['rax','rcx','rdx','r8','r9','r10','r11'];
        const prefixContexts=[];
        function prefixContext(callback, phase) {
            // Six x64 pointers followed by the two uint32_t[256] tables
            // from FastVmPrefixes. Bit i belongs to registration i.
            const masks=new Uint32Array(2*256);
            const context=Memory.alloc(48+masks.byteLength);
            [pool,state.add(8),state.add(indexOffset),state.add(indexOffset+512+4*phase),
                state.add(indexOffset+520),callback].forEach((value,i)=>context.add(i*8).writePointer(value));
            for(const item of entries) {
                if(item.phase!==phase)continue;
                const first=item.targetClass.charCodeAt(0),second=item.targetClass.charCodeAt(1)||0;
                masks[first] |= 1<<item.index;
                masks[256+second] |= 1<<item.index;
            }
            context.add(48).writeByteArray(masks.buffer);
            prefixContexts.push(context);
            return context;
        }
        function emitDispatch(callback, phase) {
        w.putPushfx();
        for (const reg of registers) w.putPushReg(reg);
        if (atInterior) {
            // Interior sites have no function-entry stack alignment guarantee.
            // Save RBP as a frame anchor and restore the exact incoming RSP.
            w.putPushReg('rbp');
            w.putBytes([0x48,0x89,0xe5,0x48,0x83,0xe4,0xf0]); // rbp=rsp; rsp&=-16
            w.putSubRegImm('rsp',0x80);
        } else w.putSubRegImm('rsp',0x88);
        for(let i=0;i<6;i++) w.putBytes([0xf3,0x0f,0x7f,0x44+(i<<3),0x24,0x20+16*i]);
        if (atInterior) w.putBytes([0x4c,0x89,0xc1]); // VM lives in R8 here; pass as RCX.
        if(prefixes) {
            w.putMovRegAddress('r8',prefixContext(callback,phase));
            w.putCallAddress(hostModule.getExportByName('EnhancedDispatchVmPrefix'));
        } else w.putCallAddress(callback);
        for(let i=0;i<6;i++) w.putBytes([0xf3,0x0f,0x6f,0x44+(i<<3),0x24,0x20+16*i]);
        if (atInterior) {
            w.putBytes([0x48,0x89,0xec]); // rsp=rbp
            w.putPopReg('rbp');
        } else w.putAddRegImm('rsp',0x88);
        for (const reg of [...registers].reverse()) w.putPopReg(reg);
        w.putPopfx();
        }
        emitDispatch(module.dispatch,0);
        if(split) {
            w.putBytes(Array.from(expected.slice(0,8)));
            emitDispatch(module.dispatch_after,1);
        }
        w.putJmpNearPtr(originalSlot);
        w.flush();
        if(w.offset>=Process.pageSize)throw Error('Fast menu gate overflow');
        w.dispose();
        if(!Memory.protect(gate,Process.pageSize,'r-x'))throw Error('Fast menu gate protection failed');
        const install = new NativeFunction(hostModule.getExportByName(split?'EnhancedInstallFastVmSplit':'EnhancedInstallFastMenu'),
            'int',['pointer','pointer','pointer','pointer','uint32']);
        const resource={state,callbacks,module,gate,originalSlot,originalBytes,frame,prefixContexts,installed:false};
        fastMenuResources.push(resource);
        const result=install(frame,gate,originalSlot,originalBytes,expected.length);
        if(result!==0)throw Error('Fast menu installation refused: '+result);
        resource.installed=true; group=resource;
    };
    attach.status=()=>({mode:'fast-native',registrations:entries.length,
        activeRegistrations:entries.filter(item=>item.active).length,
        nativeHooks:0,fastReplacements:group?.installed?1:0,
        ...(indexed?{filter:prefixes?'native-class-prefix-and-name-trie':'positive-index-and-name-trie'}:{})});
    attach.disable=()=>{
        entries.forEach(item=>{item.active=false;});
        if(group){
            group.state.add(8).writeU64(0);
            entries.forEach(item=>group.state.add(24+16*item.index).writeU64(0));
        }
    };
    // Synthetic hosts explicitly quiesce all callers before removing the gate.
    if (typeof CONFIG!=='undefined' && CONFIG.test && Process.mainModule.name.toLowerCase()!=='snowrunner.exe') {
        attach.releaseForTest=()=>{
            if(group?.installed){
                new NativeFunction(hostModule.getExportByName('EnhancedRemoveFastMenuForTest'),'void',['pointer'])(frame);
                group.installed=false;
            }
        };
    }
    return attach;
}
