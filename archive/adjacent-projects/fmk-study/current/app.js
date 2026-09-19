const PEOPLE = [
  {id:'c1',name:'Zendaya',type:'celebrity',tag:'actor · public figure',initials:'Z',base:{fuck:63,marry:78,kill:18}},
  {id:'c2',name:'Pedro Pascal',type:'celebrity',tag:'actor · public figure',initials:'PP',base:{fuck:68,marry:84,kill:14}},
  {id:'c3',name:'Janelle Monáe',type:'celebrity',tag:'artist · public figure',initials:'JM',base:{fuck:75,marry:72,kill:16}},
  {id:'c4',name:'Dev Patel',type:'celebrity',tag:'actor · public figure',initials:'DP',base:{fuck:66,marry:82,kill:13}},
  {id:'c5',name:'Megan Thee Stallion',type:'celebrity',tag:'artist · public figure',initials:'MTS',base:{fuck:82,marry:62,kill:21}},
  {id:'c6',name:'Oscar Isaac',type:'celebrity',tag:'actor · public figure',initials:'OI',base:{fuck:72,marry:73,kill:19}},
  {id:'u1',name:'Demo User 01',type:'user',tag:'ceramist · 31',initials:'01',base:{fuck:58,marry:69,kill:26}},
  {id:'u2',name:'Demo User 02',type:'user',tag:'nurse · 28',initials:'02',base:{fuck:52,marry:77,kill:21}},
  {id:'u3',name:'Demo User 03',type:'user',tag:'producer · 35',initials:'03',base:{fuck:71,marry:55,kill:30}},
  {id:'u4',name:'Demo User 04',type:'user',tag:'climber · 26',initials:'04',base:{fuck:65,marry:58,kill:29}},
  {id:'u5',name:'Demo User 05',type:'user',tag:'teacher · 33',initials:'05',base:{fuck:49,marry:81,kill:18}},
  {id:'u6',name:'Demo User 06',type:'user',tag:'barista · 25',initials:'06',base:{fuck:61,marry:64,kill:27}},
  {id:'u7',name:'Demo User 07',type:'user',tag:'tattooer · 29',initials:'07',base:{fuck:77,marry:61,kill:24}},
  {id:'u8',name:'Demo User 08',type:'user',tag:'librarian · 38',initials:'08',base:{fuck:47,marry:86,kill:12}}
];

const state = {
  route:'home',
  trio:[],
  assignments:{},
  pendingRole:'fuck',
  round:Number(localStorage.getItem('fmk-round')||1),
  votes:JSON.parse(localStorage.getItem('fmk-votes')||'{}'),
  profile:JSON.parse(localStorage.getItem('fmk-profile')||'null'),
  filter:'all'
};

const app = document.querySelector('#app');
const $ = (s,root=document)=>root.querySelector(s);
const $$ = (s,root=document)=>[...root.querySelectorAll(s)];

function clone(id){return document.querySelector(id).content.cloneNode(true)}
function save(){localStorage.setItem('fmk-votes',JSON.stringify(state.votes));localStorage.setItem('fmk-round',state.round)}
function toast(msg){const el=document.createElement('div');el.className='toast';el.textContent=msg;document.body.append(el);setTimeout(()=>el.remove(),1800)}
function sample(arr,n){const a=[...arr];for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a.slice(0,n)}
function newTrio(){
  const celebs=PEOPLE.filter(p=>p.type==='celebrity');
  const users=PEOPLE.filter(p=>p.type==='user');
  // usually mix sources: 1 celeb + 2 users, occasionally 2 celebs + 1 user
  state.trio=Math.random()>.7?[...sample(celebs,2),...sample(users,1)]:[...sample(celebs,1),...sample(users,2)];
  state.trio=sample(state.trio,3); state.assignments={}; state.pendingRole='fuck';
}
function personCard(p){return `<article class="person-card" data-id="${p.id}"><div class="source-badge">${p.type==='celebrity'?'public figure':'opt-in user'}</div><div class="portrait"><span>${p.initials}</span></div><div class="person-meta"><h3>${p.name}</h3><p>${p.tag}</p></div></article>`}
function route(name){state.route=name;location.hash=name;render()}

function render(){
  app.innerHTML='';
  if(state.route==='home') renderHome();
  if(state.route==='play') renderPlay();
  if(state.route==='results') renderResults();
  if(state.route==='profile') renderProfile();
  if(state.route==='about') renderAbout();
  window.scrollTo({top:0,behavior:'instant'});
}
function renderHome(){app.append(clone('#homeTemplate'));const total=Object.values(state.votes).reduce((a,v)=>a+(v.fuck||0)+(v.marry||0)+(v.kill||0),0);$('#homeVotes').textContent=total.toLocaleString()}
function renderPlay(){
  if(state.trio.length!==3)newTrio();app.append(clone('#playTemplate'));$('#roundNumber').textContent=state.round;$('#choiceGrid').innerHTML=state.trio.map(personCard).join('');updateAssignments();
  $$('.assignment').forEach(el=>el.addEventListener('click',()=>{state.pendingRole=el.dataset.role;updateAssignments()}));
  $$('.person-card').forEach(card=>card.addEventListener('click',()=>assign(card.dataset.id)));
  $('#skipRound').addEventListener('click',()=>{newTrio();renderPlayRoute()});
  $('#submitRound').addEventListener('click',submitRound);
}
function renderPlayRoute(){state.route='play';render()}
function assign(personId){
  const role=state.pendingRole;
  // remove person from any prior role
  for(const r of ['fuck','marry','kill']) if(state.assignments[r]===personId) delete state.assignments[r];
  // if role already filled, replace it
  state.assignments[role]=personId;
  const next=['fuck','marry','kill'].find(r=>!state.assignments[r]); if(next)state.pendingRole=next;
  updateAssignments();
}
function updateAssignments(){
  $$('.person-card').forEach(c=>{c.classList.remove('assigned-fuck','assigned-marry','assigned-kill');for(const [r,id] of Object.entries(state.assignments))if(id===c.dataset.id)c.classList.add(`assigned-${r}`)});
  $$('.assignment').forEach(el=>{const role=el.dataset.role;const id=state.assignments[role];el.classList.toggle('filled',Boolean(id));const small=el.querySelector('small');small.textContent=id?PEOPLE.find(p=>p.id===id).name:(state.pendingRole===role?'choosing this…':'tap to choose')});
  const complete=['fuck','marry','kill'].every(r=>state.assignments[r]);const btn=$('#submitRound');if(btn)btn.disabled=!complete;
}
function submitRound(){
  for(const [role,id] of Object.entries(state.assignments)){
    state.votes[id] ||= {fuck:0,marry:0,kill:0}; state.votes[id][role]++;
  }
  state.round++;save();toast('decision recorded');newTrio();renderPlayRoute();
}
function statsFor(p){
  const local=state.votes[p.id]||{fuck:0,marry:0,kill:0};
  // seed demo with synthetic prior counts so leaderboard is useful immediately
  const seedN=100;
  const f=Math.round(p.base.fuck*.32)+local.fuck;
  const m=Math.round(p.base.marry*.32)+local.marry;
  const k=Math.round(p.base.kill*.32)+local.kill;
  const total=f+m+k || seedN;
  const desirability=((f*1.0)+(m*1.35)-(k*.9))/total*100;
  return {f,m,k,total,fp:f/total*100,mp:m/total*100,kp:k/total*100,score:desirability};
}
function renderResults(){
  app.append(clone('#resultsTemplate'));renderLeaderboard();$$('.chip').forEach(c=>{c.classList.toggle('active',c.dataset.filter===state.filter);c.addEventListener('click',()=>{state.filter=c.dataset.filter;renderLeaderboard();$$('.chip').forEach(x=>x.classList.toggle('active',x.dataset.filter===state.filter))})});
}
function renderLeaderboard(){
  let arr=PEOPLE.map(p=>({...p,s:statsFor(p)}));if(state.filter!=='all')arr=arr.filter(p=>p.type===state.filter);arr.sort((a,b)=>b.s.score-a.s.score);
  $('#leaderboard').innerHTML=arr.map((p,i)=>`<tr><td>${i+1}</td><td class="rank-name">${p.name}</td><td>${p.type}</td><td class="bar-cell">${p.s.fp.toFixed(0)}%<div class="mini-bar"><i style="width:${p.s.fp}%"></i></div></td><td class="bar-cell">${p.s.mp.toFixed(0)}%<div class="mini-bar"><i style="width:${p.s.mp}%"></i></div></td><td class="bar-cell">${p.s.kp.toFixed(0)}%<div class="mini-bar"><i style="width:${p.s.kp}%"></i></div></td><td><strong>${p.s.score.toFixed(1)}</strong></td></tr>`).join('');
  const all=PEOPLE.map(p=>({...p,s:statsFor(p)}));const fuck=[...all].sort((a,b)=>b.s.fp-a.s.fp)[0];const marry=[...all].sort((a,b)=>b.s.mp-a.s.mp)[0];const kill=[...all].sort((a,b)=>b.s.kp-a.s.kp)[0];
  $('#insights').innerHTML=`<div class="insight"><span>most fucked</span><strong>${fuck.name}</strong><small>${fuck.s.fp.toFixed(0)}% of assignments</small></div><div class="insight"><span>most married</span><strong>${marry.name}</strong><small>${marry.s.mp.toFixed(0)}% of assignments</small></div><div class="insight"><span>most killed</span><strong>${kill.name}</strong><small>${kill.s.kp.toFixed(0)}% of assignments</small></div>`;
}
function renderProfile(){
  app.append(clone('#profileTemplate'));const p=state.profile;if(p){$('#displayName').value=p.name||'';$('#bio').value=p.bio||'';$('#age').value=p.age||'';$('#optIn').checked=!!p.optIn;$('#privacyAck').checked=!!p.privacyAck;$('#perspectiveAck').checked=!!p.perspectiveAck}updateProfilePreview();['displayName','bio'].forEach(id=>$('#'+id).addEventListener('input',updateProfilePreview));
  $('#profileForm').addEventListener('submit',e=>{e.preventDefault();const age=Number($('#age').value);const optIn=$('#optIn').checked;const privacyAck=$('#privacyAck').checked;const perspectiveAck=$('#perspectiveAck').checked;if(age<18){toast('18+ is required');return}if(!optIn){toast('18+ opt-in is required');return}if(!privacyAck||!perspectiveAck){toast('Please accept both acknowledgements');return}state.profile={name:$('#displayName').value.trim()||'Anonymous',bio:$('#bio').value.trim(),age,optIn,privacyAck,perspectiveAck};localStorage.setItem('fmk-profile',JSON.stringify(state.profile));updateProfilePreview();toast('profile saved locally')});
}
function updateProfilePreview(){const name=$('#displayName')?.value.trim()||state.profile?.name||'anonymous coward';const bio=$('#bio')?.value.trim()||state.profile?.bio||'your bio appears here.';$('#previewName').textContent=name;$('#previewBio').textContent=bio;$('#profileAvatar span').textContent=name.split(/\s+/).map(x=>x[0]).join('').slice(0,2).toUpperCase()||'?'}
function renderAbout(){app.append(clone('#aboutTemplate'))}

function init(){
  const requested=location.hash.replace('#','');state.route=['home','play','results','profile','about'].includes(requested)?requested:'home';
  document.addEventListener('click',e=>{const btn=e.target.closest('[data-route]');if(btn){e.preventDefault();route(btn.dataset.route)}});
  $('#resetData').addEventListener('click',()=>{localStorage.removeItem('fmk-votes');localStorage.removeItem('fmk-round');localStorage.removeItem('fmk-profile');state.votes={};state.round=1;state.profile=null;newTrio();render();toast('demo reset')});
  window.addEventListener('hashchange',()=>{const r=location.hash.replace('#','');if(['home','play','results','profile','about'].includes(r)){state.route=r;render()}});render();
}
init();
