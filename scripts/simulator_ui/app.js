const $=id=>document.getElementById(id);
let key='', state=null, last=null, busy=false;
function text(tag,value){const element=document.createElement(tag);element.textContent=value;return element;}
async function refresh(){
  try{
    const response=await fetch('/api/state',{signal:AbortSignal.timeout(12000)});
    if(!response.ok)throw new Error('Isolated backend unavailable; displayed data is stale.');
    state=await response.json();key=state.key;
    $('connection').textContent='Connected to isolated API · Gate '+state.gate+' · Updated '+new Date().toLocaleTimeString();
    if(!$('bay').options.length)for(const bay of state.bays){const option=text('option',bay.label);$('bay').append(option);}
    $('spaces').replaceChildren(...state.bays.map(bay=>{
      const card=document.createElement('article');card.className='space'+(bay.occupied?' occupied':'')+(bay.mismatch?' mismatch':'');
      card.append(text('h3',bay.label),text('p','API: '+(bay.occupied?'Occupied':'Available')),
        text('p','Sensor: '+(bay.sensor?(bay.sensor.occupied?'Occupied':'Empty'):'No reading')),
        text('p',bay.mismatch?'⚠ Reconciliation needed':(bay.plate||'No parked vehicle')));return card;
    }));
    $('events').replaceChildren(...state.events.map(event=>text('li',event.message+' · '+event.eventId.slice(0,8))));
  }catch(error){$('connection').textContent=error.message;key='';}
}
async function send(payload,replay=false){
  if(busy||!key)return;
  busy=true;for(const button of document.querySelectorAll('button'))button.disabled=true;
  if(!replay)last={eventId:crypto.randomUUID(),...payload};
  try{
    const response=await fetch('/api/events',{method:'POST',headers:{'Content-Type':'application/json','X-Simulator-Key':key},body:JSON.stringify(last),signal:AbortSignal.timeout(20000)});
    const body=await response.json();$('result').textContent=body.message+(body.replayed?' (same event replayed)':'');
  }catch{ $('result').textContent='Result uncertain. Use Replay last event to retry safely.'; }
  finally{await refresh();busy=false;for(const button of document.querySelectorAll('button'))button.disabled=false;$('repeat').disabled=!last;}
}
$('arrive').onclick=()=>send({action:'arrive',tag:$('tag').value,bay:$('bay').value});
$('depart').onclick=()=>send({action:'depart',bay:$('bay').value});
$('repeat').onclick=()=>send(null,true);
$('set-gate').onclick=()=>send({action:'gate',mode:$('gate').value});
function sensor(occupied,old=false){const bay=state?.bays.find(item=>item.label===$('bay').value);const sequence=bay?.sensor?.sequence||0;send({action:'sensor',bay:$('bay').value,occupied,sequence:old?Math.max(1,sequence-1):sequence+1});}
$('sensor-on').onclick=()=>sensor(true);$('sensor-off').onclick=()=>sensor(false);$('sensor-old').onclick=()=>sensor(false,true);
refresh();setInterval(()=>{if(!busy)refresh();},2500);
