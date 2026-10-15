const get = id => document.getElementById(id);
const database=get('database'), schema=get('schema'), table=get('table');
let page=0;
async function api(path,parameters={}) {
  const response=await fetch(path+'?'+new URLSearchParams(parameters),{cache:'no-store',signal:AbortSignal.timeout(8000)});
  const data=await response.json();
  if(!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
function options(select,items) {
  select.replaceChildren(...items.map(item => new Option(typeof item==='string'?item:item.label,typeof item==='string'?item:item.id)));
}
async function loadRows() {
  get('status').textContent='Loading records…';
  const data=await api('/api/rows',{database:database.value,schema:schema.value,table:table.value,page});
  const row=document.createElement('tr');
  for(const column of data.columns) { const cell=document.createElement('th'); cell.scope='col'; cell.textContent=column; row.append(cell); }
  get('head').replaceChildren(row); get('body').replaceChildren();
  for(const record of data.rows) {
    const row=document.createElement('tr');
    for(const value of record) { const cell=document.createElement('td'); cell.textContent=value===null?'NULL':typeof value==='object'?JSON.stringify(value):String(value); row.append(cell); }
    get('body').append(row);
  }
  get('status').textContent=`${data.total} records in ${schema.value}.${table.value}${data.total?'':'. No records saved in this table yet'}`;
  get('page').textContent=`Page ${page+1} · up to 100 records per page`;
  get('previous').disabled=page===0; get('next').disabled=(page+1)*100>=data.total;
}
async function loadTables() {
  page=0;
  const data=await api('/api/tables',{database:database.value,schema:schema.value});
  options(table,data.tables);
  if(data.tables.includes('parking_sessions')) table.value='parking_sessions';
  if(data.tables.length) await loadRows();
  else { get('status').textContent='No tables in this schema.'; get('head').replaceChildren(); get('body').replaceChildren(); }
}
async function loadSchemas() {
  const data=await api('/api/catalog');
  const selected=data.databases.find(item=>item.id===database.value);
  options(schema,selected.schemas);
  if(!selected.schemas.length) throw new Error(selected.error || 'No schemas');
  await loadTables();
}
function run(action) {
  get('refresh').disabled=true;
  void action().catch(error=>{get('status').textContent='Could not load records: '+error.message; get('head').replaceChildren(); get('body').replaceChildren();})
    .finally(()=>{get('refresh').disabled=false;});
}
database.addEventListener('change',()=>run(loadSchemas));
schema.addEventListener('change',()=>run(loadTables));
table.addEventListener('change',()=>{page=0;run(loadRows);});
get('refresh').addEventListener('click',()=>run(loadSchemas));
get('previous').addEventListener('click',()=>{page--;run(loadRows);});
get('next').addEventListener('click',()=>{page++;run(loadRows);});
run(async()=>{const data=await api('/api/catalog');options(database,data.databases);await loadSchemas();});
