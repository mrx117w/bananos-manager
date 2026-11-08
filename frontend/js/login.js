const $=s=>document.querySelector(s), form=$('#loginForm'), msg=$('#loginMsg'), btn=$('#loginBtn');
if(localStorage.getItem('bananos_token')) location='/app';
$('#eye').onclick=()=>{const p=$('#password');p.type=p.type==='password'?'text':'password';$('#eye').textContent=p.type==='password'?'VER':'OCULTAR'};
form.onsubmit=async e=>{e.preventDefault();msg.textContent='';btn.disabled=true;btn.firstChild.textContent='ENTRANDO ';
try{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('#username').value.trim(),password:$('#password').value})});const d=await r.json();if(!r.ok)throw Error(d.detail||'No se pudo iniciar sesión');localStorage.setItem('bananos_token',d.token);location='/app'}catch(err){msg.textContent=err.message;btn.disabled=false;btn.firstChild.textContent='ENTRAR '}};
