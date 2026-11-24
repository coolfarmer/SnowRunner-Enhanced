'use strict';

function makeEnhancedSettingsMenu(profile, attach = hookHudHintUpdates) {
    let hooks=[], pendingGamma=null, plan=null, patch=null, methodOwner=null;
    let poolSlot=null, running=false, state='waiting', fault=null, installations=0, visits=0;
    function obj(v){if(v.shr(48).toUInt32()!==0x20)throw Error('Expected VM object');return v.and('0xffffffffffff');}
    function untag(v){return v.and('0xffffffffffff');}
    function cls(p){return p.add(0x18).readPointer();}
    function name(id){
        if(id>0x10000000)throw Error('Invalid VM name');
        const bytes=new Uint8Array(poolSlot.readPointer().add(id).readByteArray(160));
        let n=0;while(n<bytes.length&&bytes[n]&&bytes[n]!==255)n++;
        if(n===bytes.length)throw Error('Unterminated VM name');
        return String.fromCharCode(...bytes.slice(0,n));
    }
    function className(p){return name(cls(p).add(0x18).readU32());}
    function member(p,n,kind){
        const c=cls(p),t=c.add(0x58).readPointer(),count=c.add(0x60).readU32();
        if(count>500)throw Error('Invalid class member count');
        for(let i=0;i<count;i++){
            const e=t.add(i*32);
            if(name(e.readU32())===n&&e.add(4).readU8()===kind)return {id:i,desc:e.add(8).readPointer()};
        }
        throw Error('Missing member '+n);
    }
    function prop(p,n){const slot=member(p,n,5).desc.add(0x50).readU32();if(slot>100)throw Error('Invalid property slot');return p.add(0x30+slot*8);}
    function get(p,n){return obj(prop(p,n).readPointer());}
    function method(p,n){return member(p,n,2).desc;}
    function arrayCount(p){if(className(p)!=='array')throw Error('Expected array');const n=p.add(0x48).readU32();if(n>128)throw Error('Invalid array size');return n;}
    function receiver(vm){return obj(vm.add(0x18).readPointer().readPointer());}
    function expectMembers(p, expected){
        for(const [n,id,kind] of expected)if(member(p,n,kind).id!==id)throw Error('Changed member '+n);
    }
    function restore(){
        if(!patch)return;
        const {fn,code,constants,count,words}=patch;
        if(!fn.add(0x60).readPointer().equals(plan.code)||fn.add(0x68).readU32()!==plan.words.length||
                !fn.add(0x50).readPointer().equals(plan.constants)||fn.add(0x58).readU32()!==plan.count||
                !plan.words.every((w,i)=>plan.code.add(i*4).readU32()===w))throw Error('Foreign settings bytecode; not overwritten');
        fn.add(0x60).writePointer(code);fn.add(0x68).writeU32(words);
        fn.add(0x50).writePointer(constants);fn.add(0x58).writeU32(count);patch=null;
    }
    function capture(vm){const p=receiver(vm);if(className(p)==='UiOneSettingSliderGammaController')pendingGamma=p;}
    function visit(vm,fn){
        restore();visits++;
        const self=receiver(vm);
        if(className(self)!=='UiSettingsController')throw Error('Unexpected settings receiver');
        const tabs=get(self,'activeTabs'),bar=get(self,'tabBar'),items=get(bar,'items');
        const n=arrayCount(tabs),m=arrayCount(items);
        if(n===8&&m===8){
            const last=obj(tabs.add(0x40).readPointer().add(7*8).readPointer());
            if(!plan||!prop(last,'name').readPointer().equals(plan.titleValue))throw Error('Foreign eighth settings tab');
            state='active';return; // Native objects already own our tab.
        }
        if(n!==7||m!==7)throw Error('Unsupported settings tab layout');
        if(!pendingGamma){state='waiting-for-controls';return;}
        const gamma=pendingGamma;
        if(className(gamma)!=='UiOneSettingSliderGammaController'||!get(gamma,'uiSystem').equals(get(self,'uiSystem')))
            throw Error('Unexpected brightness template');
        const original=fn.add(0x60).readPointer(),originalConstants=fn.add(0x50).readPointer(),originalCount=fn.add(0x58).readU32();
        if(name(fn.add(0x40).readPointer().readU32())!=='CreateData'||fn.add(0x68).readU32()!==profile.createDataWords.length||
                originalCount!==10||!profile.createDataWords.every((w,i)=>original.add(i*4).readU32()===w))throw Error('Settings bytecode mismatch');
        expectMembers(self,[['view',5,5],['deviceListener',8,5],['uiSystem',9,5],['localizationUpdateNotifier',11,5],
            ['inputScreen',54,5],['settings',56,5],['tabBar',57,5],['activeTabs',63,5],['GetView',34,2]]);
        expectMembers(gamma,[['header',39,5],['desc',40,5],['shouldBeVisible',41,5],['minValue',50,5],['maxValue',51,5],
            ['defaultValue',52,5],['stepInterval',53,5],['textfield',54,5],['Init',13,2]]);
        expectMembers(get(gamma,'view'),[['uiObjectDesc',5,5],['changeSound',31,5],['descriptionImage',32,5],['GetUiObject',25,2]]);
        expectMembers(bar,[['CreateItem',52,2],['UnsubscribeContent',29,2],['SubscribeContent',28,2],['Show',16,2]]);
        if(!plan){plan=build(self,gamma,fn,tabs,originalConstants,originalCount);methodOwner=fn;}
        if(!methodOwner.equals(fn))throw Error('Settings method owner changed');
        plan.gammaSlot.writePointer(gamma.or('0x20000000000000'));
        patch={fn,code:original,constants:originalConstants,count:originalCount,words:profile.createDataWords.length};
        fn.add(0x50).writePointer(plan.constants);fn.add(0x58).writeU32(plan.count);
        fn.add(0x60).writePointer(plan.code);fn.add(0x68).writeU32(plan.words.length);
        installations++;state='active';
    }
    function guarded(callback){return (...args)=>{if(fault)return;try{callback(...args);}catch(e){fault=String(e);state='incompatible';try{restore();}catch(_){};}};}
    function build(self,gamma,fn,tabs,originalConstants,originalCount){
// A bounded process-lifetime arena avoids dangling type/string constants when
// the VM keeps a reference. Its 64 KiB is released by Windows at game exit.
const va=new NativeFunction(Process.getModuleByName('kernel32.dll').getExportByName('VirtualAlloc'),'pointer',['pointer','size_t','uint32','uint32']);
const arena=va(ptr(0),65536,0x3000,4);if(arena.isNull())throw Error('Allocation failed');let used=0;
function alloc(n){n=(n+15)&~15;if(used+n>65536)throw Error('Arena full');const p=arena.add(used);used+=n;return p;}
function textValue(s){const size=encodeURIComponent(s).replace(/%[A-F\d]{2}/gi,'x').length;const b=alloc(48+size+1);b.writeU32(0x10000000);b.add(8).writeU32(size);b.add(12).writeU32(0);b.add(16).writePointer(b.add(48));b.add(24).writeU32(size+1);b.add(48).writeUtf8String(s);return b.or('0x10000000000000');}
const constants=alloc(64*8);Memory.copy(constants,originalConstants,originalCount*8);let nconst=originalCount;
function add(v){const i=nconst++;constants.add(i*8).writePointer(v);return i;}
function typeValue(c){const template=untag(originalConstants.add(5*8).readPointer()),p=alloc(48);Memory.copy(p,template,48);p.writeU32(0x10000000);p.add(8).writeU32(c.add(0x18).readU32());p.add(32).writePointer(c.or('0x3000000000000'));return p.or('0x30000000000000');}
function type(c){return add(typeValue(c));}
const preset=obj(tabs.add(0x40).readPointer().readPointer());
const presetType=type(cls(preset)),sliderType=type(cls(gamma).add(0x20).readPointer()),viewType=type(cls(get(gamma,'view')));
if(name(cls(gamma).add(0x20).readPointer().add(0x18).readU32())!=='UiOneSettingSliderController')throw Error('Wrong slider base');
const initType=add(method(self,'InitContent').add(0x50).readPointer().add(5*8).readPointer());
const title=add(textValue('ENHANCED')),category=add(textValue('MAP')),key=add(textValue('EnhancedZoom')),
 label=add(textValue('Zoom sensitivity')),description=add(textValue('Option de demonstration. Valeur temporaire, sans effet sur le zoom.')),
 empty=add(textValue('')),gammaValue=add(gamma.or('0x20000000000000'));
const infoKey=add(textValue('EnhancedAbout')),infoLabel=add(textValue('Pourquoi je vois ça?')),
 infoDesc=add(textValue('Ce menu apparaît parce que le plugin SnowRunner Enhanced est installé. Il vous permet de configurer certaines options proposées par le plugin.'));
function floatConstant(v){const p=alloc(8);p.writeFloat(v);p.add(6).writeU16(3);return add(p.readPointer());}
const zero=floatConstant(0),hundred=floatConstant(100),fifty=floatConstant(50),one=floatConstant(1);
// Typed stack assembler; function arguments are pushed in reverse order.
const W=(op,arg=0)=>(((arg+0x800000)*256)+op)>>>0;
const L=i=>[W(7,i)],C=i=>[W(6,i)],I=i=>[W(4,i)],B=i=>[W(5,i)];
const field=(value,id)=>[...value,W(10,id)];
const S=id=>field(L(0),id);
function call(receiver,id,args=[]){return [W(1,1),...args.slice().reverse().flat(),...receiver,W(4,args.length),W(13,id)];}
function stmt(v){return [...v,W(2)];}
function set(receiver,id,value){return [...value,...receiver,W(60,id),W(2)];}
function assign(local,value){return [...value,W(59,local),W(2)];}
function create(local,t){return assign(local,[W(1,1),W(57,t),W(4,0),W(58,t)]);}
function append(array,value){return [...value,...array,W(66),W(2)];}
const prefix=[W(1,17),
 ...create(-9,presetType),...set(L(-9),6,C(title)),
 ...create(-10,5),...set(L(-10),4,C(infoKey)),...set(L(-10),5,B(0)),...append(field(L(-9),4),L(-10)),
 ...create(-10,3),...set(L(-10),4,C(category)),...append(field(L(-9),4),L(-10)),
 ...create(-11,5),...set(L(-11),4,C(key)),...set(L(-11),5,B(0)),...append(field(L(-9),4),L(-11)),
 ...create(-12,sliderType),...create(-13,viewType),
 ...set(L(-13),5,field(field(C(gammaValue),5),5)),
 ...set(L(-13),31,field(field(C(gammaValue),5),31)),...set(L(-13),32,C(empty)),
 ...set(L(-12),5,L(-13)),...set(L(-12),39,C(label)),...set(L(-12),40,C(description)),...set(L(-12),41,B(1)),
 ...set(L(-12),50,C(zero)),...set(L(-12),51,C(hundred)),...set(L(-12),52,C(fifty)),...set(L(-12),53,C(one)),...set(L(-12),54,I(1)),
 ...create(-14,initType),...set(L(-14),6,S(8)),...set(L(-14),7,S(11)),...set(L(-14),8,S(9)),...set(L(-14),9,S(54)),
 ...stmt(call(L(-12),13,[L(-14)])),
 // Reuse the native selectable row, with its value control hidden. This
 // informational row has only a title and contextual help, no game action.
 ...create(-16,sliderType),...create(-17,viewType),
 ...set(L(-17),5,field(field(C(gammaValue),5),5)),...set(L(-17),32,C(empty)),
 ...set(L(-16),5,L(-17)),...set(L(-16),39,C(infoLabel)),...set(L(-16),40,C(infoDesc)),...set(L(-16),41,B(1)),
 ...set(L(-16),50,C(zero)),...set(L(-16),51,C(hundred)),...set(L(-16),52,C(fifty)),...set(L(-16),53,C(one)),...set(L(-16),54,I(1)),
 ...stmt(call(L(-16),13,[L(-14)])),
 ...set(field(call(L(-17),25),144),24,B(0)),
 ...stmt(call(S(56),5,[C(infoKey),L(-16)])),
 ...stmt(call(S(56),5,[C(key),L(-12)])),...append(S(63),L(-9)),
 ...assign(-15,call([W(8)],127,[C(title),C(title)])),
 ...set(L(-15),5,field(call(call(L(0),34),25),148)),
 ...stmt(call(S(57),52,[L(-15)])),...stmt(call(S(57),29)),...stmt(call(S(57),28)),...stmt(call(S(57),16,[B(0)]))
];
function relocated(words,delta){return words.map(w=>[0x16,0x17,0x18,0x19,0x1a].includes(w&255)?W(w&255,(w>>>8)-0x800000+delta):w);}
function code(words){const p=alloc(words.length*4);words.forEach((w,i)=>p.add(i*4).writeU32(w));return {p,words};}
const install=code([...prefix,...relocated(profile.createDataWords.slice(1),prefix.length-1)]);
return {code:install.p,words:install.words,constants,count:nconst,gammaSlot:constants.add(gammaValue*8),titleValue:constants.add(title*8).readPointer(),bytes:used};
    }
    return {
        start(framePush,stringPoolSlot){
            if(running)throw Error('Settings menu already started');poolSlot=stringPoolSlot;
            try{
                hooks.push(attach(framePush,poolSlot,guarded(()=>{pendingGamma=null;}),'UiSettingsController','InitContent'));
                hooks.push(attach(framePush,poolSlot,guarded(capture),'UiOneSettingSliderController','InitContent'));
                // Also supports attachment after the game has initialized its settings.
                hooks.push(attach(framePush,poolSlot,guarded(capture),'UiOneSettingSliderGammaController','GetCurrentValue'));
                hooks.push(attach(framePush,poolSlot,guarded(visit),'UiSettingsController','CreateData'));
                running=true;state='waiting-for-settings';
            }catch(e){for(const h of hooks)h.detach();Interceptor.flush();hooks=[];throw e;}
        },
        status(){return {enabled:true,status:state,running,installations,visits,fault,arenaBytes:plan?plan.bytes:0};},
        stop(){for(const h of hooks)h.detach();Interceptor.flush();hooks=[];restore();running=false;state='stopped';}
    };
}
