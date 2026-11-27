'use strict';

// Game-thread-only access to SSL values. Returned native values are owned and
// released after each callback; cached names and program storage are bounded.
function makeTruckSearchVm(profile, poolSlot) {
    const base=Process.mainModule.base, strings=new Map(), functions=new Map(), members=new Map();
    const scratch=Memory.alloc(128), owned=[];
    const release=new NativeFunction(base.add(profile.variantReleaseRva),'void',['pointer']);
    const untag=v=>v.and('0xffffffffffff'), cls=p=>p.add(24).readPointer();
    function name(id){
        if(id>0x10000000)throw Error('Invalid SSL name');
        const bytes=new Uint8Array(poolSlot.readPointer().add(id).readByteArray(200));
        const end=bytes.findIndex(b=>b===0||b===255);
        if(end<0)throw Error('Unterminated SSL name');
        return String.fromCharCode(...bytes.slice(0,end));
    }
    const className=p=>name(cls(p).add(24).readU32());
    function member(p,n,kind){
        const c=cls(p),key=c+':'+n+':'+kind;
        if(members.has(key))return members.get(key);
        if(members.size>4096)throw Error('Search metadata cache limit');
        const table=c.add(0x58).readPointer(),count=c.add(0x60).readU32();
        if(count>1500)throw Error('Invalid SSL class');
        for(let i=0;i<count;i++){
            const e=table.add(i*32),k=e.add(4).readU8();
            if((kind===undefined||k===kind)&&name(e.readU32())===n){const found={id:i,kind:k,desc:e.add(8).readPointer()};members.set(key,found);return found;}
        }
        throw Error('Missing SSL member '+n);
    }
    function prop(p,n){const slot=member(p,n,5).desc.add(0x50).readU32();if(slot>512)throw Error('Invalid SSL slot');return p.add(0x30+slot*8);}
    const get=(p,n)=>untag(prop(p,n).readPointer());
    function str(v){
        if(v.shr(48).toUInt32()!==16)return '';
        const p=untag(v),n=p.add(8).readU32();if(n>16384)throw Error('Invalid SSL string');
        return (p.add(12).readU32()===1?p.add(16):p.add(16).readPointer()).readUtf8String(n)||'';
    }
    function text(s){
        if(strings.has(s))return strings.get(s).value;
        if(strings.size>128)throw Error('Search string cache limit');
        const n=encodeURIComponent(s).replace(/%[A-F\d]{2}/gi,'x').length,p=Memory.alloc(49+n);
        p.writeU32(0x10000000);p.add(8).writeU32(n);p.add(12).writeU32(0);
        p.add(16).writePointer(p.add(48));p.add(24).writeU32(n+1);p.add(48).writeUtf8String(s);
        const value=p.or('0x10000000000000');strings.set(s,{p,value});return value;
    }
    function fn(p,result,args){
        const key=p+':'+args.length;if(!functions.has(key))functions.set(key,new NativeFunction(p,result,args));
        return functions.get(key);
    }
    function native(p,n,vm,args=[]){
        if(args.length>8)throw Error('Too many native arguments');
        args.forEach((v,i)=>scratch.add(i*8).writePointer(v));const out=scratch.add(96);out.writePointer(ptr(0));
        const error=fn(member(p,n,1).desc.add(0x50).readPointer(),'uint8',['pointer','pointer','uint','pointer','pointer'])(vm,p,args.length,scratch,out);
        const value=out.readPointer();owned.push(value);if(error)throw Error('Native call '+n);return value;
    }
    function read(p,n,vm){
        const m=member(p,n);if(m.kind===5)return prop(p,n).readPointer();
        if(m.kind!==4)throw Error('Expected native property');
        const out=scratch.add(96);out.writePointer(ptr(0));
        const error=fn(m.desc.add(0x58).readPointer(),'uint8',['pointer','pointer','uint','pointer'])(vm,p,0,out);
        const value=out.readPointer();owned.push(value);if(error)throw Error('Native getter '+n);return value;
    }
    function write(p,n,value,vm){
        scratch.writePointer(value);
        if(fn(member(p,n,4).desc.add(0x50).readPointer(),'uint8',['pointer','pointer','uint','pointer'])(vm,p,1,scratch))throw Error('Native setter '+n);
    }
    function drop(value){scratch.add(112).writePointer(value);release(scratch.add(112));}
    function scoped(cb){const mark=owned.length;try{return cb();}finally{while(owned.length>mark)drop(owned.pop());}}
    function float(value){scratch.add(80).writeFloat(value);scratch.add(84).writeU32(0x30000);return scratch.add(80).readPointer();}
    const bool=v=>ptr(v?'0x2000000000001':'0x2000000000000');
    const integer=v=>ptr(v>>>0).or('0x1000000000000');
    function array(p){
        if(className(p)!=='array')throw Error('Expected SSL array');
        const n=p.add(0x48).readU32();if(n>5000)throw Error('Search array limit');
        const values=p.add(0x40).readPointer();return Array.from({length:n},(_,i)=>values.add(i*8).readPointer());
    }
    return {untag,cls,className,member,prop,get,str,text,native,read,write,drop,scoped,float,bool,integer,array,
        tag:p=>p.or('0x20000000000000'),receiver:vm=>untag(vm.add(24).readPointer().readPointer()),
        child:(p,n,vm)=>untag(native(p,'GetChildByName',vm,[text(n)]))};
}

function makeTruckSearchGfx(profile) {
    const base=Process.mainModule.base,keys=new Map(),values=[];
    const getFn=new NativeFunction(base.add(profile.gfxGetRva),'uint8',['pointer','pointer','pointer','pointer','uint8']);
    const setFn=new NativeFunction(base.add(profile.gfxSetRva),'uint8',['pointer','pointer','pointer','pointer','uint8']);
    const invokeFn=new NativeFunction(base.add(profile.gfxInvokeRva),'uint8',['pointer','pointer','pointer','pointer','pointer','uint','uint8']);
    const release=new NativeFunction(base.add(profile.gfxReleaseRva),'void',['pointer','pointer','pointer']);
    const payload=new NativeFunction(base.add(profile.payloadOffsetRva),'int',['pointer']);
    function key(s){if(!keys.has(s))keys.set(s,Memory.allocUtf8String(s));return keys.get(s);}
    function blank(){const p=Memory.alloc(48);p.writeByteArray(new Uint8Array(48));values.push(p);return p;}
    const display=p=>(p.add(24).readU32()&15)===10?1:0;
    function get(o,n){const p=blank();if(!getFn(o.add(16).readPointer(),o.add(32).readPointer(),key(n),p,display(o)))throw Error('GFx getter '+n);return p;}
    function value(v){const p=blank();p.add(24).writeU32(typeof v==='boolean'?2:typeof v==='number'?5:6);if(typeof v==='boolean')p.add(32).writeU8(v?1:0);else if(typeof v==='number')p.add(32).writeDouble(v);else p.add(32).writePointer(key(v));return p;}
    function set(o,n,v){if(!setFn(o.add(16).readPointer(),o.add(32).readPointer(),key(n),typeof v==='object'?v:value(v),display(o)))throw Error('GFx setter '+n);}
    function invoke(o,n,args=[]){
        const a=Memory.alloc(Math.max(48,args.length*48)),out=blank();
        args.forEach((v,i)=>Memory.copy(a.add(i*48),typeof v==='object'?v:value(v),48));
        if(!invokeFn(o.add(16).readPointer(),o.add(32).readPointer(),out,key(n),a,args.length,display(o)))throw Error('GFx invoke '+n);
        return out;
    }
    function object(p){const offset=payload(p.add(24));if(offset<0||offset>4096)throw Error('Invalid native payload');return p.add(offset+8).readPointer();}
    function clear(){while(values.length){const p=values.pop();if(p.add(24).readU32()&64)release(p.add(16).readPointer(),p,p.add(32).readPointer());}}
    return {get,set,invoke,object,clear};
}
