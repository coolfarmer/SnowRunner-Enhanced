/* Enhancement #6. Initialization logic derived from SnowRunner FFB Fix,
 * Copyright (c) 2026 coolfarmer, MIT (Licenses/SnowRunnerFFBFix.txt).
 * Discovery is relocatable; only instruction-relative addresses are wildcarded.
 * The constructor callback stays native and does no allocation or file I/O. */
#pragma once
#include <stdint.h>
#include <string.h>
#include <stdio.h>

typedef struct { unsigned offset, size, next, target; int code; } SwRef;
typedef struct { const char *name; unsigned rva, size; const unsigned char *bytes, *mask; const SwRef *refs; unsigned count; } SwSignature;
typedef struct { unsigned rva, size; int code, readable; } SwSection;
typedef struct { unsigned old_rva, new_rva; } SwFact;
#include "steering_profile.h"

static volatile LONG sw_armed;
static volatile LONG64 sw_applied, sw_failed, sw_skipped;
static const char *sw_state = "disabled";
static char sw_reason[192] = "Not selected";
static unsigned sw_relocated;
static GumInvocationListener *sw_listener;

static BOOL SwContained(const SwSection *sections, unsigned count, unsigned rva, unsigned size, BOOL code) {
    for (unsigned i=0;i<count;i++) {
        const SwSection *s=sections+i;
        if (s->readable && (!code || s->code) && rva>=s->rva && rva-s->rva<=s->size && size<=s->size-(rva-s->rva)) return TRUE;
    }
    return FALSE;
}

static BOOL SwFactAdd(SwFact *facts, unsigned *count, unsigned old, unsigned value) {
    for (unsigned i=0;i<*count;i++) if (facts[i].old_rva==old) return facts[i].new_rva==value;
    if (*count>=4096) return FALSE;
    facts[*count]=(SwFact){old,value}; ++*count; return TRUE;
}

/* Pure resolver shared by the production loader and synthetic relocation tests.
 * Copies of executable sections are supplied by the caller. Never scans data. */
static BOOL SwResolve(const unsigned char *image, size_t size, const SwSection *sections, unsigned section_count,
                     const SwSignature *sigs, unsigned count, unsigned constructor, unsigned *found, unsigned *target) {
    SwFact *facts=g_new0(SwFact,4096); unsigned fact_count=0; BOOL ok=FALSE;
    unsigned *candidates=g_new0(unsigned,(size_t)count*16384), *counts=g_new0(unsigned,count);
    for (unsigned i=0;i<count;i++) {
        const SwSignature *s=sigs+i; unsigned anchor=0;
        while (anchor<s->size && !s->mask[anchor]) ++anchor;
        if (anchor==s->size) { snprintf(sw_reason,sizeof(sw_reason),"Invalid signature: %s",s->name); goto done; }
        for (unsigned k=0;k<section_count;k++) {
            const SwSection *sec=sections+k;
            if (!sec->code || !sec->readable || sec->rva>size || sec->size>size-sec->rva || sec->size<s->size) continue;
            const unsigned char *p=image+sec->rva+anchor, *end=image+sec->rva+sec->size-s->size+anchor+1;
            while (p<end && (p=memchr(p,s->bytes[anchor],(size_t)(end-p)))!=NULL) {
                const unsigned char *candidate=p-anchor; unsigned j=0; ++p;
                for (;j<s->size;j++) if (s->mask[j] && candidate[j]!=s->bytes[j]) break;
                if (j!=s->size) continue;
                if (counts[i]==16384) { snprintf(sw_reason,sizeof(sw_reason),"Too many candidates: %s",s->name); goto done; }
                candidates[i*16384+counts[i]++]=(unsigned)(candidate-image);
            }
        }
        if (!counts[i]) { snprintf(sw_reason,sizeof(sw_reason),"Missing or changed signature: %s",s->name); goto done; }
    }
    BOOL changed;
    do {
        changed=FALSE;
        /* Unique long guards establish the identities of their short callees. */
        for (unsigned i=0;i<count;i++) if (counts[i]==1) {
            const SwSignature *s=sigs+i; unsigned rva=candidates[i*16384];
            if (!SwFactAdd(facts,&fact_count,s->rva,rva)) goto inconsistent;
            for (unsigned k=0;k<count;k++) {
                unsigned symbol=sigs[k].rva;
                if (symbol>=s->rva && symbol-s->rva<s->size && !SwFactAdd(facts,&fact_count,symbol,rva+symbol-s->rva)) goto inconsistent;
                for (unsigned n=0;n<sigs[k].count;n++) {
                    symbol=sigs[k].refs[n].target;
                    if (symbol>=s->rva && symbol-s->rva<s->size && !SwFactAdd(facts,&fact_count,symbol,rva+symbol-s->rva)) goto inconsistent;
                }
            }
            for (unsigned j=0;j<s->count;j++) {
                const SwRef *ref=s->refs+j; int32_t displacement=0;
                if ((ref->size!=1 && ref->size!=4) || ref->offset>s->size || ref->size>s->size-ref->offset) goto inconsistent;
                if (ref->size==1) displacement=(int8_t)image[rva+ref->offset];
                else memcpy(&displacement,image+rva+ref->offset,4);
                int64_t destination=(int64_t)rva+ref->next+displacement;
                if (destination<0 || destination>UINT32_MAX || !SwContained(sections,section_count,(unsigned)destination,1,ref->code) ||
                    !SwFactAdd(facts,&fact_count,ref->target,(unsigned)destination)) goto inconsistent;
            }
        }
        for (unsigned i=0;i<count;i++) {
            const SwSignature *s=sigs+i; unsigned kept=0;
            for (unsigned k=0;k<counts[i];k++) {
                unsigned rva=candidates[i*16384+k]; BOOL valid=TRUE;
                for (unsigned n=0;n<fact_count && valid;n++) {
                    unsigned symbol=facts[n].old_rva;
                    if (symbol>=s->rva && symbol-s->rva<s->size && facts[n].new_rva!=rva+symbol-s->rva) valid=FALSE;
                }
                for (unsigned j=0;j<s->count && valid;j++) {
                    const SwRef *ref=s->refs+j; int32_t displacement=0;
                    if ((ref->size!=1 && ref->size!=4) || ref->offset>s->size || ref->size>s->size-ref->offset) goto inconsistent;
                    if (ref->size==1) displacement=(int8_t)image[rva+ref->offset];
                    else memcpy(&displacement,image+rva+ref->offset,4);
                    int64_t destination=(int64_t)rva+ref->next+displacement;
                    if (destination<0 || destination>UINT32_MAX || !SwContained(sections,section_count,(unsigned)destination,1,ref->code)) { valid=FALSE; break; }
                    for (unsigned n=0;n<fact_count;n++)
                        if (facts[n].old_rva==ref->target && facts[n].new_rva!=(unsigned)destination) { valid=FALSE; break; }
                }
                if (valid) candidates[i*16384+kept++]=rva;
            }
            if (!kept) goto inconsistent;
            if (kept!=counts[i]) { changed=TRUE; counts[i]=kept; }
        }
    } while (changed);
    for (unsigned i=0;i<count;i++) {
        if (counts[i]!=1) { snprintf(sw_reason,sizeof(sw_reason),"Ambiguous signature after reference checks: %s",sigs[i].name); goto done; }
        found[i]=candidates[i*16384];
    }
    for (unsigned i=0;i<fact_count;i++) if (facts[i].old_rva==constructor) { *target=facts[i].new_rva; ok=TRUE; goto done; }
inconsistent:
    snprintf(sw_reason,sizeof(sw_reason),"Inconsistent code references or object layout");
done:
    g_free(facts); g_free(candidates); g_free(counts); return ok;
}

static void SwInitializeFields(void *object) {
    DWORD error=GetLastError();
    if (!InterlockedCompareExchange(&sw_armed,0,0)) InterlockedIncrement64(&sw_skipped);
    else {
        uintptr_t p=(uintptr_t)object, target=p+0x44; uint64_t zero[2]={0,0}, after[2]={1,1};
        MEMORY_BASIC_INFORMATION m; SIZE_T written=0, read=0;
        if (p && target>p && target+16>target && VirtualQuery((void *)target,&m,sizeof(m))==sizeof(m) &&
            m.State==MEM_COMMIT && m.Type==MEM_PRIVATE && m.Protect==PAGE_READWRITE &&
            target>=(uintptr_t)m.BaseAddress && target-(uintptr_t)m.BaseAddress<=m.RegionSize &&
            m.RegionSize-(target-(uintptr_t)m.BaseAddress)>=16 &&
            WriteProcessMemory(GetCurrentProcess(),(void *)target,zero,16,&written) && written==16 &&
            ReadProcessMemory(GetCurrentProcess(),(void *)target,after,16,&read) && read==16 && !after[0] && !after[1])
            InterlockedIncrement64(&sw_applied);
        else { InterlockedIncrement64(&sw_failed); InterlockedExchange(&sw_armed,0); }
    }
    SetLastError(error);
}

static void SwOnEnter(GumInvocationContext *context, gpointer unused) {
    (void)unused;
    SwInitializeFields(gum_invocation_context_get_nth_argument(context,0));
}

static BOOL SwAttach(void *target) {
    GumInterceptor *interceptor=gum_interceptor_obtain();
    sw_listener=gum_make_call_listener(SwOnEnter,NULL,NULL,NULL);
    InterlockedExchange(&sw_armed,1);
    GumAttachReturn result=gum_interceptor_attach(interceptor,target,sw_listener,NULL);
    if (result!=GUM_ATTACH_OK) {
        InterlockedExchange(&sw_armed,0); g_object_unref(sw_listener); sw_listener=NULL;
        snprintf(sw_reason,sizeof(sw_reason),"Native interception refused (%d)",result);
    }
    g_object_unref(interceptor); return result==GUM_ATTACH_OK;
}

static BOOL SwLiveCode(const void *address, size_t length) {
    uintptr_t cursor=(uintptr_t)address, end=cursor+length;
    if (!cursor || !length || end<=cursor) return FALSE;
    while (cursor<end) {
        MEMORY_BASIC_INFORMATION m;
        if (VirtualQuery((void *)cursor,&m,sizeof(m))!=sizeof(m) || m.State!=MEM_COMMIT ||
            (m.Protect&(PAGE_GUARD|PAGE_NOACCESS)) ||
            !(m.Protect&(PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY))) return FALSE;
        uintptr_t next=(uintptr_t)m.BaseAddress+m.RegionSize;
        if (next<=cursor) return FALSE;
        cursor=next<end?next:end;
    }
    return TRUE;
}

static void SteeringInstall(void) {
    unsigned char *base=(unsigned char *)GetModuleHandleW(NULL), *image=NULL;
    const IMAGE_DOS_HEADER *dos=(const IMAGE_DOS_HEADER *)base;
    sw_state="incompatible"; snprintf(sw_reason,sizeof(sw_reason),"Invalid executable sections");
    if (dos->e_magic!=IMAGE_DOS_SIGNATURE || dos->e_lfanew<0 || dos->e_lfanew>0x100000) return;
    const IMAGE_NT_HEADERS64 *nt=(const IMAGE_NT_HEADERS64 *)(base+dos->e_lfanew);
    if (nt->Signature!=IMAGE_NT_SIGNATURE || nt->FileHeader.Machine!=IMAGE_FILE_MACHINE_AMD64 || nt->OptionalHeader.Magic!=IMAGE_NT_OPTIONAL_HDR64_MAGIC) return;
    unsigned count=nt->FileHeader.NumberOfSections, size=nt->OptionalHeader.SizeOfImage;
    if (!count || count>96 || !size || size>512u*1024*1024) return;
    SwSection sections[96]; const IMAGE_SECTION_HEADER *pe=IMAGE_FIRST_SECTION(nt);
    image=g_try_malloc0(size); if (!image) { sw_state="error"; strcpy(sw_reason,"Discovery allocation failed"); return; }
    for (unsigned i=0;i<count;i++) {
        sections[i]=(SwSection){pe[i].VirtualAddress,pe[i].Misc.VirtualSize,
            !!(pe[i].Characteristics&IMAGE_SCN_MEM_EXECUTE),!!(pe[i].Characteristics&IMAGE_SCN_MEM_READ)};
        SwSection *s=sections+i;
        if (s->rva>size || s->size>size-s->rva) goto done;
        if (s->code && s->readable && s->size) {
            SIZE_T read=0;
            if (!ReadProcessMemory(GetCurrentProcess(),base+s->rva,image+s->rva,s->size,&read) || read!=s->size) goto done;
        }
    }
    unsigned found[G_N_ELEMENTS(sw_signatures)], target=0;
    if (!SwResolve(image,size,sections,count,sw_signatures,G_N_ELEMENTS(sw_signatures),SW_CONSTRUCTOR_RVA,found,&target)) goto done;
    /* Re-read every byte used for discovery immediately before attaching. */
    for (unsigned i=0;i<G_N_ELEMENTS(sw_signatures);i++) {
        unsigned length=sw_signatures[i].size; unsigned char *current=g_malloc(length); SIZE_T read=0;
        BOOL same=SwLiveCode(base+found[i],length) && ReadProcessMemory(GetCurrentProcess(),base+found[i],current,length,&read) && read==length && !memcmp(current,image+found[i],length);
        g_free(current);
        if (!same) { strcpy(sw_reason,"Code changed during discovery"); goto done; }
        if (found[i]!=sw_signatures[i].rva) ++sw_relocated;
    }
    if (SwAttach(base+target)) { sw_state="active"; strcpy(sw_reason,"Constructor resolved by signatures and references"); }
    else sw_state="error";
done:
    g_free(image);
}

static JsonObject *SteeringStatus(BOOL enabled) {
    JsonObject *status=json_object_new(); LONG64 failed=InterlockedCompareExchange64(&sw_failed,0,0);
    json_object_set_boolean_member(status,"enabled",enabled);
    json_object_set_string_member(status,"status",failed?"faulted":sw_state);
    json_object_set_string_member(status,"reason",failed?"Memory initialization failed; correction disarmed":sw_reason);
    json_object_set_string_member(status,"compatibilityMethod","signatures-and-references");
    json_object_set_int_member(status,"relocatedGuards",sw_relocated);
    json_object_set_boolean_member(status,"armed",InterlockedCompareExchange(&sw_armed,0,0)!=0);
    json_object_set_int_member(status,"applied",InterlockedCompareExchange64(&sw_applied,0,0));
    json_object_set_int_member(status,"failed",failed);
    json_object_set_int_member(status,"skipped",InterlockedCompareExchange64(&sw_skipped,0,0));
    return status;
}
