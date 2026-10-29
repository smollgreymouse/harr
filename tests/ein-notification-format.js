const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('common/mcp/ein_app/panel.html','utf8');
const code=html.match(/function briefHandoff\(h\)\{[\s\S]*?\n\}/)[0];
const ctx={instance:'gigacode'};vm.createContext(ctx);vm.runInContext(code,ctx);
const handoff={session_id:'bf4e5b41-0b86-46dc-a11d-25d072a6dc4c',status:'FAILED',summary:'GigaCode process failed before producing a usable handoff.',changed:[],verified:[],escalation:null,blockers:[{kind:'tool',detail:'gigacode exited with code -15',evidence:'GigaCode cancelled: owning MCP process exited.'}],runtime:{phase:'finished',job_id:'1859cadf4144',elapsed_sec:375.8,exit_code:-15}};
const text=ctx.briefHandoff(handoff);
for(const value of ['ошибка',handoff.summary,handoff.session_id,'1859cadf4144','375.8','-15','tool','GigaCode cancelled: owning MCP process exited.'])assert(text.includes(value),value);
assert(!text.includes('{"status"'));
console.log(text);console.log('Compact Ein notification: PASS');
