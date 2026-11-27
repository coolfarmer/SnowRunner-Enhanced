'use strict';

// Only user-visible strings belong here. Keys used by the settings dictionary are stable.
const enhancedMenuText = {
    // The two VM strings have distinct identities to track the locale of an existing tab.
    title: ['ENHANCED', 'ENHANCED'],
    category: ['MAP', 'CARTE'],
    featuresCategory: ['FEATURES', 'FONCTIONNALITÉS'],
    featureWheel: ['Simultaneous Mouse & Wheel Input', 'Utilisation simultanée souris et volant'],
    featureStartup: ['Skip Startup Logos', 'Passer les logos de démarrage'],
    featureMap: ['Map Improvements/Options', 'Améliorations et options de la carte'],
    featureGeneral: ['General Improvements', 'Améliorations générales'],
    featureVehicle: ['Vehicle Improvement/Options', 'Améliorations et options du véhicule'],
    featureSteering: ['Steering Wheel Improvements', 'Améliorations du volant'],
    featureInactive: ['Inactive', 'Inactif'],
    featurePending: ['Pending', 'En attente'],
    featureActive: ['Active', 'Actif'],
    featureError: ['Error', 'Erreur'],
    featureInactiveHelp: ['Disabled in the installer. To enable this feature, close the game and use the installer.',
        'Désactivé dans l’installateur. Pour activer cette fonctionnalité, fermez le jeu et utilisez l’installateur.'],
    featurePendingHelp: ['Selected in the installer. Waiting for initialization or for the relevant game screen to load. This is not an error.',
        'Sélectionné dans l’installateur. En attente de l’initialisation ou du chargement de l’écran concerné. Ce n’est pas une erreur.'],
    featureActiveHelp: ['Initialized successfully, with no detected error. This status is checked during the current game session.',
        'Initialisé correctement, sans erreur détectée. Cet état est vérifié pendant la session de jeu en cours.'],
    featureErrorHelp: ['At least one correction could not start or encountered an error. Export a diagnostic from the installer for details.',
        'Au moins un correctif n’a pas pu démarrer ou a rencontré une erreur. Exportez un diagnostic depuis l’installateur pour obtenir les détails.'],
    infoLabel: ['Why am I seeing this?', 'Pourquoi cet onglet ?'],
    infoDesc: ['SnowRunner Enhanced adds this tab so you can configure the plugin in the game settings. Grayed-out options belong to a disabled module. Enable that module in the installer to use its options.',
        'SnowRunner Enhanced ajoute cet onglet pour vous permettre de configurer le plugin dans les paramètres du jeu. Les options grisées appartiennent à un module désactivé. Activez ce module dans l’installateur pour accéder à ses options.'],
    zoomLabel: ['Zoom sensitivity', 'Sensibilité du zoom'],
    zoomDesc: ['Adjusts map zoom speed. At 50, zoom uses the original game speed. At 0, it is four times slower. At 100, it is four times faster. Changes are applied and saved immediately.',
        'Règle la vitesse du zoom sur la carte. À 50, le zoom conserve la vitesse d’origine du jeu. À 0, il est quatre fois plus lent. À 100, il est quatre fois plus rapide. Les changements sont appliqués et sauvegardés immédiatement.'],
    panningLabel: ['Panning sensitivity', 'Sensibilité de rotation'],
    panningDesc: ['Adjusts how fast the map rotates while you hold the right mouse button. At 50, rotation uses the original game speed. At 0, it is fifty times slower. At 100, it is four times faster. Changes are applied and saved immediately.',
        'Règle la vitesse de rotation de la carte lorsque vous maintenez le bouton droit de la souris. À 50, la carte tourne à la vitesse d’origine du jeu. À 0, elle tourne cinquante fois plus lentement. À 100, elle tourne quatre fois plus vite. Les changements sont appliqués et sauvegardés immédiatement.'],
    vehicleCategory: ['VEHICLE', 'VÉHICULE'],
    searchLabel: ['Truck Storage search', 'Recherche dans le stockage de camions'],
    searchDesc: ['Show a search field in Truck Storage to filter your trucks as you type.',
        'Affiche un champ de recherche dans le stockage de camions pour filtrer la liste pendant la saisie.'],
    reverseLabel: ['Automatic reverse', 'Marche arrière automatique'],
    reverseDesc: ['In AUTO, holding the brake after stopping engages reverse. Turn this off to select R manually.',
        'En AUTO, maintenir le frein après l’arrêt engage la marche arrière. Désactivez cette option pour sélectionner R manuellement.'],
    northLabel: ['Keep North Up', 'Garder le nord en haut'],
    northDesc: ['Keeps north at the top of the map. Turn this off to rotate the map freely.',
        'Garde le nord en haut de la carte. Désactivez cette option pour tourner la carte librement.'],
    off: ['Off', 'Désactivé'],
    on: ['On', 'Activé']
};

// Section IDs match the installer configuration. All rows in a section inherit
// its navigation, mouse and display state; the About row belongs to the core UI.
const enhancedMenuSections = [
    {module: 'map', category: 'category', rows: [
        {key: 'EnhancedZoom', kind: 'slider', label: 'zoomLabel', help: 'zoomDesc'},
        {key: 'EnhancedPanning', kind: 'slider', label: 'panningLabel', help: 'panningDesc'},
        {key: 'EnhancedKeepNorthUp', kind: 'toggle', label: 'northLabel', help: 'northDesc', initial: 0}
    ]},
    {module: 'vehicle', category: 'vehicleCategory', rows: [
        {key: 'EnhancedAutomaticReverse', kind: 'toggle', label: 'reverseLabel', help: 'reverseDesc', initial: 1},
        {key: 'EnhancedTruckStorageSearch', kind: 'toggle', label: 'searchLabel', help: 'searchDesc', initial: 1}
    ]}
];
const enhancedMenuFeatures = [
    ['wheel_mouse', 'featureWheel'], ['skip_startup_logos', 'featureStartup'],
    ['map', 'featureMap'], ['general_improvements', 'featureGeneral'],
    ['vehicle', 'featureVehicle'], ['steering_wheel_improvements', 'featureSteering']
];

function makeEnhancedSettingsMenu(profile, attach = hookHudHintUpdates, options = {}) {
    let hooks=[], pendingGamma=null, pendingStepper=null, plan=null, patch=null, methodOwner=null;
    let localePatch=null;
    let pulsePatch=null;
    let poolSlot=null, running=false, state='waiting', fault=null, installations=0, visits=0;
    const modules=options.modules ?? {map: options.mapEnabled!==false, vehicle: options.vehicleEnabled===true};
    const mapEnabled=modules.map===true;
    const vehicleEnabled=modules.vehicle===true;
    function featureSnapshot(){
        const reported=options.getFeatureStates?.() || {};
        return Object.fromEntries(enhancedMenuFeatures.map(([id])=>[id,
            ['inactive','pending','active','error'].includes(reported[id]) ? reported[id] : modules[id]===true?'pending':'inactive']));
    }
    function restorePulse(){
        if(!pulsePatch)return;
        const {fn,original}=pulsePatch;
        if(!fn.add(0x60).readPointer().equals(plan.pulse.p)||fn.add(0x68).readU32()!==plan.pulse.words.length||
                !plan.pulse.words.every((w,i)=>plan.pulse.p.add(i*4).readU32()===w))throw Error('Foreign status refresh bytecode');
        fn.add(0x60).writePointer(original);fn.add(0x68).writeU32(profile.featurePulseWords.length);pulsePatch=null;
    }
    function pulse(vm,fn){
        restorePulse();
        if(!plan)return;
        const self=receiver(vm);
        if(className(self)!=='UiSettingsController'||arrayCount(get(self,'activeTabs'))!==8)return;
        plan.updateFeatures(featureSnapshot());
        if(!plan.featuresDirty())return;
        const original=fn.add(0x60).readPointer();
        if(fn.add(0x68).readU32()!==profile.featurePulseWords.length||
            !profile.featurePulseWords.every((w,i)=>original.add(i*4).readU32()===w))throw Error('Unsupported settings refresh');
        pulsePatch={fn,original};fn.add(0x60).writePointer(plan.pulse.p);fn.add(0x68).writeU32(plan.pulse.words.length);
    }
    const zoom=makeMapZoomSensitivity(profile,{receiver,prop,get,owns:p=>ownsRow(p,'UiOneSettingSliderController','zoomLabel')},{...options,mapEnabled},attach);
    const panning=makeMapPanningSensitivity(profile,{receiver,prop,get,owns:p=>ownsRow(p,'UiOneSettingSliderController','panningLabel')},{...options,mapEnabled},attach);
    let automaticReverse=options.automaticReverse!==false;
    let truckStorageSearch=options.truckStorageSearch!==false;
    let northUp=options.keepNorthUp===true, cameraClass=null, northFault=null;
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
        return classMember(cls(p),n,kind);
    }
    function classMember(c,n,kind){
        const t=c.add(0x58).readPointer(),count=c.add(0x60).readU32();
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
        const {fn,code,constants,count,words,program}=patch;
        if(!fn.add(0x60).readPointer().equals(program.p)||fn.add(0x68).readU32()!==program.words.length||
                !fn.add(0x50).readPointer().equals(plan.constants)||fn.add(0x58).readU32()!==plan.count||
                !program.words.every((w,i)=>program.p.add(i*4).readU32()===w))throw Error('Foreign settings bytecode; not overwritten');
        fn.add(0x60).writePointer(code);fn.add(0x68).writeU32(words);
        fn.add(0x50).writePointer(constants);fn.add(0x58).writeU32(count);patch=null;
    }
    function capture(vm){const p=receiver(vm);if(className(p)==='UiOneSettingSliderGammaController')pendingGamma=p;}
    function captureStepper(vm){
        if(pendingStepper)return;
        const control=receiver(vm);
        // The native on/off settings supply a view with the correct arrow clip.
        for(let c=cls(control).add(0x20).readPointer();!c.isNull();c=c.add(0x20).readPointer()){
            if(name(c.add(0x18).readU32())!=='UiOneSettingStepperOnOff')continue;
            if(className(get(control,'view'))==='UiOneSettingStepperView')pendingStepper={control,base:c};
            return;
        }
    }
    function ownsRow(control,kind,key){
        return !!plan && className(control)===kind && plan.matches(key,prop(control,'header').readPointer());
    }
    function ownsNorth(control){return ownsRow(control,'UiOneSettingStepperOnOff','northLabel');}
    function localeIndex(value){
        if(value.shr(48).toUInt32()!==16)return 0;
        const s=untag(value);
        if(s.isNull())return 0;
        const length=s.add(8).readU32();
        if(!length||length>128)return 0;
        const data=s.add(12).readU32()===1?s.add(16):s.add(16).readPointer();
        if(data.isNull())return 0;
        try{
            const language=data.readUtf8String(length).trim();
            return /^(?:fr|fra|fre|french|français)(?:$|[-_])/i.test(language)?1:0;
        }catch(_){return 0;}
    }
    function setMenuLocale(vm){
        if(!plan)return;
        const control=receiver(vm);
        if(!ownsRow(control,'UiOneSettingSliderController','infoLabel'))return;
        plan.selectLocale(localeIndex(vm.add(0x18).readPointer().add(8).readPointer()));
    }
    function restoreLocale(){
        if(!localePatch)return;
        const {fn,code}=localePatch;
        if(!fn.add(0x60).readPointer().equals(plan.redraw.p)||fn.add(0x68).readU32()!==plan.redraw.words.length||
                !plan.redraw.words.every((w,i)=>plan.redraw.p.add(i*4).readU32()===w))
            throw Error('Foreign settings locale bytecode; not overwritten');
        fn.add(0x60).writePointer(code);fn.add(0x68).writeU32(plan.localeWords.length);localePatch=null;
    }
    function settingsLocale(vm,fn){
        restoreLocale();
        if(!plan)return;
        const self=receiver(vm);
        if(className(self)!=='UiSettingsController')return;
        plan.selectLocale(localeIndex(vm.add(0x18).readPointer().add(8).readPointer()));
        const tabs=untag(prop(self,'activeTabs').readPointer());
        if(tabs.isNull()||arrayCount(tabs)!==8)return;
        const preset=obj(tabs.add(0x40).readPointer().add(7*8).readPointer());
        const title=prop(preset,'name').readPointer();
        if(!plan.matches('title',title)||plan.current('title').equals(title))return;
        const code=fn.add(0x60).readPointer();
        if(!method(self,'SetForLocale').equals(fn)||fn.add(0x68).readU32()!==plan.localeWords.length||
                !plan.localeWords.every((w,i)=>code.add(i*4).readU32()===w))
            throw Error('Unsupported settings locale method');
        localePatch={fn,code};
        fn.add(0x60).writePointer(plan.redraw.p);fn.add(0x68).writeU32(plan.redraw.words.length);
    }
    function changeStepper(vm){
        const control=receiver(vm);
        const reverse=vehicleEnabled&&ownsRow(control,'UiOneSettingStepperOnOff','reverseLabel');
        const search=vehicleEnabled&&ownsRow(control,'UiOneSettingStepperOnOff','searchLabel');
        if(!reverse&&!search&&!(mapEnabled&&ownsNorth(control)))return;
        const arg=vm.add(0x18).readPointer().add(8);
        if(arg.readPointer().shr(48).toUInt32()!==2)throw Error('Invalid on/off argument');
        // VM comparisons write only the low byte of a tagged boolean.
        const next=arg.readU8()!==0;
        // The on/off base implements UpdateStatus as a no-op. Its inherited
        // GetCurrentIndex reads hackCurrent on the ensuing native view refresh.
        if(reverse && next!==automaticReverse){options.onReverseChange?.(next);automaticReverse=next;}
        if(search && next!==truckStorageSearch){options.onSearchChange?.(next);truckStorageSearch=next;}
        prop(control,'hackCurrent').writePointer(ptr(next?'0x1000000000001':'0x1000000000000'));
        if(!reverse&&!search&&northUp!==next){northUp=next;options.onNorthChange?.(next);}
    }
    function orientCamera(vm,fn){
        if(!northUp||northFault)return;
        try{
            const camera=receiver(vm),c=cls(camera);
            if(!cameraClass||!cameraClass.equals(c)){
                if(className(camera)!=='MinimapCameraController'||!fn.add(0x48).readPointer().equals(c)||
                   !method(camera,'UpdateImpl').equals(fn))throw Error('Unexpected map camera');
                const rotation=member(camera,'rotation',5);
                const words=profile.mapUpdateWords,code=fn.add(0x60).readPointer();
                if(rotation.id!==31||rotation.desc.add(0x50).readU32()!==26||
                   fn.add(0x68).readU32()!==words.length||!words.every((w,i)=>code.add(i*4).readU32()===w))
                    throw Error('Unsupported map camera layout');
                cameraClass=c;
            }
            const rotation=camera.add(0x30+26*8);
            if(rotation.readPointer().shr(48).toUInt32()!==3||!Number.isFinite(rotation.readFloat()))
                throw Error('Invalid map rotation');
            if(rotation.readFloat()!==0)rotation.writeFloat(0);
        }catch(e){northFault=String(e);}
    }
    function visit(vm,fn){
        restore();visits++;
        if(plan)plan.updateFeatures(featureSnapshot());
        const self=receiver(vm);
        if(className(self)!=='UiSettingsController')throw Error('Unexpected settings receiver');
        const tabs=get(self,'activeTabs'),bar=get(self,'tabBar'),items=get(bar,'items');
        const n=arrayCount(tabs),m=arrayCount(items);
        if(n===8&&m===8){
            const last=obj(tabs.add(0x40).readPointer().add(7*8).readPointer());
            const title=prop(last,'name').readPointer();
            if(!plan||!plan.matches('title',title))throw Error('Foreign eighth settings tab');
            if(plan.current('title').equals(title)&&!plan.featuresDirty()){state='active';return;}
            // The native view keeps its rendered label. Refresh it along with the
            // preset before CreateData lays out the selected tab in the new locale.
        }else if(n!==7||m!==7)throw Error('Unsupported settings tab layout');
        if(n===7&&(!pendingGamma||!pendingStepper)){state='waiting-for-controls';return;}
        const gamma=pendingGamma;
        const original=fn.add(0x60).readPointer(),originalConstants=fn.add(0x50).readPointer(),originalCount=fn.add(0x58).readU32();
        if(name(fn.add(0x40).readPointer().readU32())!=='CreateData'||fn.add(0x68).readU32()!==profile.createDataWords.length||
                originalCount!==10||!profile.createDataWords.every((w,i)=>original.add(i*4).readU32()===w))throw Error('Settings bytecode mismatch');
        if(n===7){
            if(className(gamma)!=='UiOneSettingSliderGammaController'||!get(gamma,'uiSystem').equals(get(self,'uiSystem')))
                throw Error('Unexpected brightness template');
            expectMembers(self,[['view',5,5],['deviceListener',8,5],['uiSystem',9,5],['localizationUpdateNotifier',11,5],
                ['inputScreen',54,5],['settings',56,5],['tabBar',57,5],['activeTabs',63,5],['GetView',34,2],['UpdateViewData',24,2]]);
            expectMembers(gamma,[['header',39,5],['desc',40,5],['shouldBeVisible',41,5],['minValue',50,5],['maxValue',51,5],
                ['defaultValue',52,5],['stepInterval',53,5],['textfield',54,5],['Init',13,2]]);
            expectMembers(get(gamma,'view'),[['uiObjectDesc',5,5],['changeSound',31,5],['descriptionImage',32,5],['GetUiObject',25,2]]);
            expectMembers(bar,[['CreateItem',52,2],['UnsubscribeContent',29,2],['SubscribeContent',28,2],['Show',16,2],['items',65,5],['UpdateTabsOffset',82,2]]);
            if(!plan){plan=build(self,gamma,fn,tabs,originalConstants,originalCount);methodOwner=fn;}
            plan.updateFeatures(featureSnapshot());
            plan.gammaSlot.writePointer(gamma.or('0x20000000000000'));
            if(!get(pendingStepper.control,'uiSystem').equals(get(self,'uiSystem')))throw Error('Unexpected on/off template');
            plan.stepperSlot.writePointer(pendingStepper.control.or('0x20000000000000'));
            plan.indexSlots.EnhancedAutomaticReverse.writePointer(ptr(automaticReverse?'0x1000000000001':'0x1000000000000'));
            plan.indexSlots.EnhancedTruckStorageSearch.writePointer(ptr(truckStorageSearch?'0x1000000000001':'0x1000000000000'));
            plan.indexSlots.EnhancedKeepNorthUp.writePointer(ptr(northUp?'0x1000000000001':'0x1000000000000'));
        }
        if(!methodOwner.equals(fn))throw Error('Settings method owner changed');
        const program=n===7?plan.install:plan.refresh;
        patch={fn,program,code:original,constants:originalConstants,count:originalCount,words:profile.createDataWords.length};
        fn.add(0x50).writePointer(plan.constants);fn.add(0x58).writeU32(plan.count);
        fn.add(0x60).writePointer(program.p);fn.add(0x68).writeU32(program.words.length);
        plan.featuresRendered();
        if(n===7)installations++;state='active';
    }
    function guarded(callback){
        return (...args)=>{
            if(fault)return;
            try{callback(...args);}catch(e){
                fault=String(e);state='incompatible';
                try{restore();}catch(_){}
                try{restoreLocale();}catch(_){}
                try{restorePulse();}catch(_){}
            }
        };
    }
    function build(self,gamma,fn,tabs,originalConstants,originalCount){
// A bounded process-lifetime arena avoids dangling type/string constants when
// the VM keeps a reference. Its 64 KiB is released by Windows at game exit.
const va=new NativeFunction(Process.getModuleByName('kernel32.dll').getExportByName('VirtualAlloc'),'pointer',['pointer','size_t','uint32','uint32']);
const arena=va(ptr(0),65536,0x3000,4);if(arena.isNull())throw Error('Allocation failed');let used=0;
function alloc(n){n=(n+15)&~15;if(used+n>65536)throw Error('Arena full');const p=arena.add(used);used+=n;return p;}
function textValue(s){const size=encodeURIComponent(s).replace(/%[A-F\d]{2}/gi,'x').length;const b=alloc(48+size+1);b.writeU32(0x10000000);b.add(8).writeU32(size);b.add(12).writeU32(0);b.add(16).writePointer(b.add(48));b.add(24).writeU32(size+1);b.add(48).writeUtf8String(s);return b.or('0x10000000000000');}
const capacity=originalCount+Object.keys(enhancedMenuText).length+32+enhancedMenuFeatures.length*6+enhancedMenuSections.reduce((n,section)=>n+section.rows.length*2,0);
const constants=alloc(capacity*8);Memory.copy(constants,originalConstants,originalCount*8);let nconst=originalCount;
function add(v){if(nconst>=capacity)throw Error('Too many menu constants');const i=nconst++;constants.add(i*8).writePointer(v);return i;}
function typeValue(c){const template=untag(originalConstants.add(5*8).readPointer()),p=alloc(48);Memory.copy(p,template,48);p.writeU32(0x10000000);p.add(8).writeU32(c.add(0x18).readU32());p.add(32).writePointer(c.or('0x3000000000000'));return p.or('0x30000000000000');}
function type(c){return add(typeValue(c));}
const preset=obj(tabs.add(0x40).readPointer().readPointer());
const presetType=type(cls(preset)),sliderType=type(cls(gamma).add(0x20).readPointer()),viewType=type(cls(get(gamma,'view')));
if(name(cls(gamma).add(0x20).readPointer().add(0x18).readU32())!=='UiOneSettingSliderController')throw Error('Wrong slider base');
const initType=add(method(self,'InitContent').add(0x50).readPointer().add(5*8).readPointer());
const variants={},slots={};
for(const [key,pair] of Object.entries(enhancedMenuText)){
    variants[key]=pair.map(textValue);
    slots[key]=add(variants[key][0]);
}
const current=key=>constants.add(slots[key]*8).readPointer();
const matches=(key,value)=>variants[key].some(v=>v.equals(value));
let featureLocale=0,featureStates={},featureDirty=true;
const featureSlots={};
const stateNames={inactive:'Inactive',pending:'Pending',active:'Active',error:'Error'};
// UiDisplayObjectBase.color uses packed ARGB, including opacity. RGB alone
// sets alpha to zero and makes the entire value control transparent.
const colorValues={inactive:0xffff6666,pending:0xffffcc66,active:0xff66dd88,error:0xffff6666};
for(const [id] of enhancedMenuFeatures)featureSlots[id]={
    value:add(variants.featurePending[0]),help:add(variants.featurePendingHelp[0]),color:add(ptr(colorValues.pending).or('0x1000000000000'))
};
function updateFeatures(states){
    if(JSON.stringify(states)!==JSON.stringify(featureStates))featureDirty=true;
    featureStates=states;
    for(const [id] of enhancedMenuFeatures){
        const state=states[id]||'pending',key='feature'+stateNames[state],row=featureSlots[id];
        constants.add(row.value*8).writePointer(variants[key][featureLocale]);
        constants.add(row.help*8).writePointer(variants[key+'Help'][featureLocale]);
        constants.add(row.color*8).writePointer(ptr(colorValues[state]).or('0x1000000000000'));
    }
}
function selectLocale(index){
    featureLocale=index;
    for(const key of Object.keys(slots))constants.add(slots[key]*8).writePointer(variants[key][index]);
    updateFeatures(featureStates);
}
const {title,infoLabel,infoDesc}=slots;
const infoKey=add(textValue('EnhancedAbout'));
const empty=add(textValue('')),gammaValue=add(gamma.or('0x20000000000000'));
const getLocale=member(get(self,'uiSystem'),'GetCurrentLocale',2).id;
expectMembers(gamma,[['SetForLocale',33,2]]);
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
// The preset's skip flag removes the row from native list navigation. Dim the
// row clip (alpha is a percentage) and block mouse input to its children too.
const dimmedAlpha=floatConstant(45);
function disableView(enabled){
    if(enabled)return [];
    const clip=call(L(-13),25);
    return [...set(clip,25,C(dimmedAlpha)),...set(clip,22,B(0)),...set(clip,23,B(0))];
}
const sectionRows=[],sectionRefresh=[],stepperData={indexSlots:{}};
{
    const template=pendingStepper.control;
    expectMembers(template,[['view',5,5],['header',39,5],['desc',40,5],['shouldBeVisible',41,5],
        ['defaultStepperIndex',50,5],['hackCurrent',51,5],['SetForLocale',33,2],['Init',13,2]]);
    expectMembers(get(template,'view'),[['uiObjectDesc',5,5],['changeSound',31,5],['descriptionImage',32,5],
        ['updateCurrentWithoutNotification',41,5],['UpdateStepperCurrent',43,2],['GetUiObject',25,2]]);
    const stepper=type(pendingStepper.base),stepView=type(cls(get(template,'view')));
    const stepSource=add(template.or('0x20000000000000'));
    stepperData.stepperSlot=constants.add(stepSource*8);
    // The native on/off initializer constructs array<string> from constant 1.
    const initializer=classMember(pendingStepper.base,'CreateInitialData',2).desc;
    if(initializer.add(0x58).readU32()<2)throw Error('Missing stepper value array type');
    const arrayType=initializer.add(0x50).readPointer().add(8).readPointer();
    if(arrayType.shr(48).toUInt32()!==0x30)throw Error('Unexpected stepper value array type');
    const stringsType=add(arrayType);
    const choices=[
        ...create(-10,stringsType),...append(L(-10),C(slots.off)),...append(L(-10),C(slots.on)),
        ...set(L(-13),41,B(1)), // Suppress change notifications while replacing the displayed choices.
        ...stmt(call(field(call(L(-13),25),144),96,[L(-10)])),
        ...stmt(call(L(-13),43,[field(L(-12),51)]))
    ];
    function slider(label,help){
        return [
           ...create(-12,sliderType),...create(-13,viewType),
           ...set(L(-13),5,field(field(C(gammaValue),5),5)),
           ...set(L(-13),31,field(field(C(gammaValue),5),31)),...set(L(-13),32,C(empty)),
           ...set(L(-12),5,L(-13)),...set(L(-12),39,C(label)),...set(L(-12),40,C(help)),...set(L(-12),41,B(1)),
           ...set(L(-12),50,C(zero)),...set(L(-12),51,C(hundred)),...set(L(-12),52,C(fifty)),...set(L(-12),53,C(one)),...set(L(-12),54,I(2)),
            ...stmt(call(L(-12),13,[L(-14)]))
        ];
    }
    function toggle(row,label,help,values=choices){
        const index=add(ptr(row.initial?'0x1000000000001':'0x1000000000000'));
        stepperData.indexSlots[row.key]=constants.add(index*8);
        return [
            ...create(-12,stepper),...set(L(-12),39,C(label)),...set(L(-12),40,C(help)),
            ...create(-13,stepView),...set(L(-13),5,field(field(C(stepSource),5),5)),
            ...set(L(-13),31,field(field(C(stepSource),5),31)),...set(L(-13),32,C(empty)),
            ...set(L(-12),5,L(-13)),...set(L(-12),41,B(1)),...set(L(-12),50,I(row.initial)),...set(L(-12),51,C(index)),
            ...stmt(call(L(-12),13,[L(-14)])),...values
        ];
    }
    let position=1; // The About row is first.
    sectionRows.push(...create(-10,3),...set(L(-10),4,C(slots.featuresCategory)),...append(field(L(-9),4),L(-10)));
    sectionRefresh.push(...set(at(field(L(-9),4),position),4,C(slots.featuresCategory)));
    position+=1+enhancedMenuFeatures.length;
    for(const [id,labelName] of enhancedMenuFeatures){
        const row=featureSlots[id],key=add(textValue('EnhancedFeature_'+id)),label=slots[labelName];
        const clip=call(L(-13),25),stepperClip=field(clip,144);
        // A single choice cannot be toggled, even by keyboard/controller or
        // Restore Defaults. Keep the row selectable for its contextual help.
        const values=[...create(-10,stringsType),...append(L(-10),C(row.value)),
            ...set(L(-13),41,B(1)),...stmt(call(stepperClip,96,[L(-10)])),
            ...stmt(call(L(-13),43,[I(0)])),
            ...set(stepperClip,35,C(row.color)),
            ...set(stepperClip,22,B(0)),...set(stepperClip,23,B(0)),
            ...set(field(stepperClip,105),24,B(0)),...set(field(stepperClip,106),24,B(0))];
        sectionRows.push(...create(-11,5),...set(L(-11),4,C(key)),...set(L(-11),5,B(0)),
            ...append(field(L(-9),4),L(-11)),
            ...toggle({key:'EnhancedFeature_'+id,initial:0},label,row.help,values),
            ...stmt(call(S(56),5,[C(key),L(-12)])));
        sectionRefresh.push(...refreshRow(key,label,row.help),...values);
    }
    for(const section of enhancedMenuSections){
        const enabled=modules[section.module]===true, category=C(slots[section.category]);
        sectionRows.push(...create(-10,3),...set(L(-10),4,category),...append(field(L(-9),4),L(-10)));
        sectionRefresh.push(...set(at(field(L(-9),4),position),4,category));
        position+=1+section.rows.length;
        for(const row of section.rows){
            const key=add(textValue(row.key)),label=slots[row.label],help=slots[row.help];
            let control;
            switch(row.kind){
                case 'slider': control=slider(label,help);break;
                case 'toggle': control=toggle(row,label,help);break;
                default: throw Error('Unknown menu control '+row.kind);
            }
            sectionRows.push(...create(-11,5),...set(L(-11),4,C(key)),...set(L(-11),5,B(enabled?0:1)),
                ...append(field(L(-9),4),L(-11)),...control,...disableView(enabled),...stmt(call(S(56),5,[C(key),L(-12)])));
            sectionRefresh.push(...refreshRow(key,label,help));
            if(row.kind==='toggle')sectionRefresh.push(...choices);
        }
    }
}
function refreshRow(key,label,help){
    return [
        ...assign(-12,[...C(key),...S(56),W(68)]),...assign(-13,field(L(-12),5)),
        ...set(L(-12),39,C(label)),...set(L(-12),40,C(help)),
        // Both slider and stepper InitContent set textCont.tfContainer.tf.text.
        ...set(field(field(field(call(L(-13),25),143),145),143),97,C(label))
    ];
}
const prefix=[W(1,17),
 // Read the game locale before the first caption is consumed, including when Map is disabled.
 ...create(-16,sliderType),...set(L(-16),39,C(infoLabel)),...stmt(call(L(-16),33,[call(S(9),getLocale)])),
 ...create(-9,presetType),...set(L(-9),6,C(title)),
 ...create(-10,5),...set(L(-10),4,C(infoKey)),...set(L(-10),5,B(0)),...append(field(L(-9),4),L(-10)),
 ...create(-14,initType),...set(L(-14),6,S(8)),...set(L(-14),7,S(11)),...set(L(-14),8,S(9)),...set(L(-14),9,S(54)),
 // Reuse the native selectable row, with its value control hidden. This
 // informational row has only a title and contextual help, no game action.
 ...create(-17,viewType),
 ...set(L(-17),5,field(field(C(gammaValue),5),5)),...set(L(-17),32,C(empty)),
 ...set(L(-16),5,L(-17)),...set(L(-16),39,C(infoLabel)),...set(L(-16),40,C(infoDesc)),...set(L(-16),41,B(1)),
 ...set(L(-16),50,C(zero)),...set(L(-16),51,C(hundred)),...set(L(-16),52,C(fifty)),...set(L(-16),53,C(one)),...set(L(-16),54,I(1)),
 ...stmt(call(L(-16),13,[L(-14)])),
 ...set(field(call(L(-17),25),144),24,B(0)),
 ...stmt(call(S(56),5,[C(infoKey),L(-16)])),
 ...sectionRows,
 ...append(S(63),L(-9)),
 ...assign(-15,call([W(8)],127,[C(title),C(title)])),
 ...set(L(-15),5,field(call(call(L(0),34),25),148)),
 ...stmt(call(S(57),52,[L(-15)])),...stmt(call(S(57),29)),...stmt(call(S(57),28)),...stmt(call(S(57),16,[B(0)]))
];
function relocated(words,delta){return words.map(w=>[0x16,0x17,0x18,0x19,0x1a].includes(w&255)?W(w&255,(w>>>8)-0x800000+delta):w);}
function code(words){const p=alloc(words.length*4);words.forEach((w,i)=>p.add(i*4).writeU32(w));return {p,words};}
function at(array,index){return [...I(index),...array,W(63)];}
const refreshPrefix=[W(1,17),
    ...assign(-9,at(S(63),7)),...set(L(-9),6,C(title)),
    ...refreshRow(infoKey,infoLabel,infoDesc),...sectionRefresh,
    // UiSettingsTabElementView uses tfCont.tf.text; recompute native tab widths afterward.
    ...assign(-13,call(at(field(S(57),65),7),34)),
    ...set(field(field(call(L(-13),25),141),143),97,C(title)),...stmt(call(S(57),82))
];
function program(prefix){return code([...prefix,...relocated(profile.createDataWords.slice(1),prefix.length-1)]);}
// The native locale callback updates the tab bar only. Also ask the settings
// controller to redraw its current tab through its usual CreateData path.
const localeWords=[W(1,1),...L(1),...L(0),...I(1),...C(0),W(14,33),W(2),
    ...stmt(call(S(57),33,[L(1)])),W(19,2)];
const redraw=code([...localeWords.slice(0,-1),...stmt(call(L(0),24)),W(19,2)]);
const pulse=code([W(1,1),...stmt(call(L(0),24)),...profile.featurePulseWords.slice(1)]);
return {...stepperData,redraw,localeWords,pulse,updateFeatures,featuresDirty:()=>featureDirty,featuresRendered:()=>{featureDirty=false;},install:program(prefix),refresh:program(refreshPrefix),constants,count:nconst,
    gammaSlot:constants.add(gammaValue*8),matches,current,selectLocale,bytes:used};
    }
    return {
        start(framePush,stringPoolSlot){
            if(running)throw Error('Settings menu already started');poolSlot=stringPoolSlot;
            try{
                hooks.push(attach(framePush,poolSlot,guarded(()=>{pendingGamma=null;pendingStepper=null;}),'UiSettingsController','InitContent'));
                hooks.push(attach(framePush,poolSlot,guarded(setMenuLocale),'ComponentUiControllerBase','SetForLocale'));
                hooks.push(attach(framePush,poolSlot,guarded(settingsLocale),'UiSettingsController','SetForLocale'));
                hooks.push(attach(framePush,poolSlot,guarded(pulse),'UiSettingsController','HandleInputScreenUpdate'));
                hooks.push(attach(framePush,poolSlot,guarded(captureStepper),'UiOneSettingStepperController','InitContent'));
                hooks.push(attach(framePush,poolSlot,guarded(changeStepper),'UiOneSettingStepperOnOff','UpdateStatus'));
                if(mapEnabled)hooks.push(attach(framePush,poolSlot,orientCamera,'MinimapCameraController','UpdateImpl'));
                hooks.push(attach(framePush,poolSlot,guarded(capture),'UiOneSettingSliderController','InitContent'));
                // Also supports attachment after the game has initialized its settings.
                hooks.push(attach(framePush,poolSlot,guarded(capture),'UiOneSettingSliderGammaController','GetCurrentValue'));
                hooks.push(attach(framePush,poolSlot,guarded(visit),'UiSettingsController','CreateData'));
                zoom.start(framePush,poolSlot);panning.start(framePush,poolSlot);
                if(attach.commit)attach.commit();
                running=true;state='waiting-for-settings';
            }catch(e){for(const h of hooks)h.detach();Interceptor.flush();hooks=[];try{zoom.stop();}finally{panning.stop();}throw e;}
        },
        status(){return {enabled:true,status:state,running,installations,visits,fault,arenaBytes:plan?plan.bytes:0,zoomSensitivity:zoom.status(),panningSensitivity:panning.status(),keepNorthUp:{enabled:mapEnabled&&northUp,fault:northFault},...(attach.status?{interception:attach.status()}:{})};},
        stop(){for(const h of hooks)h.detach();Interceptor.flush();hooks=[];try{zoom.stop();}finally{try{panning.stop();}finally{try{restore();}finally{try{restoreLocale();}finally{restorePulse();}}running=false;state='stopped';}}}
    };
}
