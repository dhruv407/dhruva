import assert from 'node:assert/strict';
import {chromium} from '@playwright/test';

// This test mutates only the dedicated loopback Docker staging database.
const base='http://127.0.0.1:8088';
// The platform egress proxy is for external HTTPS. These checks use only the
// loopback test gateway, so avoid routing local requests to that proxy.
for (const key of ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']) delete process.env[key];
process.env.NO_PROXY='127.0.0.1,localhost,::1';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
const context=await browser.newContext({baseURL:base,httpCredentials:{username:'tester',password:'test-only-login'},viewport:{width:1440,height:1000}});
const page=await context.newPage();
const errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(60000);
async function json(path,body){
 const response=body===undefined?await context.request.get('/api'+path):await context.request.post('/api'+path,{data:body});
 assert.ok(response.ok(),await response.text());return response.json();
}
try {
 const anonymous=await fetch(base+'/api/dashboard');assert.equal(anonymous.status,401);
 const before=await json('/dashboard');assert.equal(before.snapshot_id,3);assert.equal(before.ageing.length,14151);
 await page.goto('/');await page.getByText(/Stock #3 · 2026-10-14/).waitFor();
 await page.getByText('Test workspace: approvals and movement records apply to this isolated test copy.').waitFor();
 assert.equal(await page.getByText('Private test workspace',{exact:true}).count(),1);
 await page.getByRole('button',{name:'Natural diamonds',exact:true}).click();
 await page.getByText(/Natural diamonds · values are kept separate/).waitFor();
 await page.getByRole('button',{name:'Lab-grown diamonds',exact:true}).click();
 await page.getByText(/Lab-grown diamonds · values are kept separate/).waitFor();
 await page.getByRole('button',{name:'Gold',exact:true}).click();
 await page.getByRole('button',{name:'Ageing & reactivation',exact:true}).click();
 await page.getByRole('heading',{name:'Label ageing register'}).waitFor();
 await page.getByRole('button',{name:/^Rebalance proposals/}).click();
 await page.getByRole('heading',{name:'Label-level movement proposals'}).waitFor();
 await page.getByRole('textbox',{name:'Operator identity'}).fill('Isolated staging browser test');
 await page.getByRole('button',{name:'Planning rules',exact:true}).click();
 const draftName='Staging acceptance '+Date.now();
 await page.getByRole('textbox',{name:'New draft name',exact:true}).fill(draftName);
 const created=page.waitForResponse(r=>r.url().endsWith('/api/rules')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Save as new draft'}).click();const rule=await (await created).json();
 await page.getByRole('combobox',{name:'Selected rule version'}).selectOption(String(rule.id));
 assert.ok(await page.getByRole('button',{name:'Activate approved rule'}).isDisabled());
 const denied=await context.request.post(`/api/rules/${rule.id}/activate`,{data:{actor:'test'}});assert.equal(denied.status(),422);
 await page.getByRole('button',{name:/^Rebalance proposals/}).click();
 await page.getByRole('combobox',{name:'Rule version',exact:true}).selectOption(String(rule.id));
 const simulated=page.waitForResponse(r=>r.url().endsWith('/api/simulations')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Run simulation',exact:true}).click();const simulation=await (await simulated).json();assert.equal(simulation.rule_id,rule.id);
 await page.getByRole('button',{name:'Compare against active rules'}).click();
 await page.getByText('Comparison saved on identical source snapshots').waitFor();
 await page.getByRole('button',{name:'Planning rules',exact:true}).click();
 await page.getByRole('combobox',{name:'Selected rule version'}).selectOption(String(rule.id));
 await page.getByRole('button',{name:'Approve compared rule',exact:true}).click();await page.getByText('Rule approved',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Activate approved rule',exact:true}).click();await page.getByText('Rule activated',{exact:true}).waitFor();
 const transfer=simulation.transfers.find(t=>t.purpose==='rebalance');assert.ok(transfer);
 const original=before.ageing.find(f=>f.label_id===transfer.labels[0]);assert.ok(original);
 await json(`/transfers/${transfer.id}/action`,{actor:'Isolated staging browser test',action:'approve',reference:'STAGE-APPROVAL'});
 await json(`/transfers/${transfer.id}/action`,{actor:'Isolated staging browser test',action:'dispatch',reference:'STAGE-DISPATCH'});
 assert.equal((await json('/dashboard')).ageing.find(f=>f.label_id===original.label_id).branch,'IN_TRANSIT');
 await json(`/transfers/${transfer.id}/action`,{actor:'Isolated staging browser test',action:'receive',reference:'STAGE-RECEIPT'});
 const received=(await json('/dashboard')).ageing.find(f=>f.label_id===original.label_id);
 assert.equal(received.received_at,original.received_at);assert.equal(received.branch,transfer.route.at(-1));
 const events=await json('/audit');assert.ok(events.some(e=>e.action==='dispatch'&&e.entity_id===transfer.id));assert.ok(events.some(e=>e.action==='receive'&&e.entity_id===transfer.id));
 await page.getByRole('button',{name:'Stock overview',exact:true}).click();
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({anonymous_inventory:'401 denied',compiled_ui:true,source_labels:before.ageing.length,material_tabs:'passed',ageing:'passed',rule_lifecycle:'draft → simulate → compare → approve → activate',transfer_ledger:'approve → dispatch → receive',original_age:'preserved',mobile:'passed',browser_errors:0,test_database:'isolated rg-stock-test only'},null,2));
} finally {await context.close();await browser.close();}
