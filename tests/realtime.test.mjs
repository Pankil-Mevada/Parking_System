import {test} from 'node:test';
import assert from 'node:assert/strict';
import {changedResources} from '../frontend/realtime.ts';
test('replay ignores duplicate IDs and old versions, but accepts another space',()=>{
 const versions=new Map([['space-a',3n]]);
 assert.equal(changedResources([{id:'10',aggregate_id:'space-a',aggregate_version:'4'}],'10',versions),false);
 assert.equal(changedResources([{id:'11',aggregate_id:'space-a',aggregate_version:'2'}],'10',versions),false);
 assert.equal(changedResources([{id:'12',aggregate_id:'space-b',aggregate_version:'1'}],'10',versions),true);
 assert.equal(changedResources([{id:'12',aggregate_id:'space-b',aggregate_version:'1'}],'10',versions),false);
 assert.equal(changedResources([{id:'13',aggregate_id:'space-a',aggregate_version:'4'}],'12',versions),true);
 assert.equal(versions.get('space-a'),4n);
});
test('malformed and out-of-order notifications cannot regress a known space',()=>{
 const versions=new Map([['space',8n]]);
 assert.equal(changedResources([{id:'bad',aggregate_id:'space',aggregate_version:'9'},{id:'19',aggregate_id:'space',aggregate_version:'7'}],'18',versions),false);
 assert.equal(versions.get('space'),8n);
});
