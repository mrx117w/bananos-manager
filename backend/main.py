from pathlib import Path
from datetime import datetime, timedelta
import os, uuid
from io import BytesIO
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, String, Integer, Float, Boolean, DateTime, ForeignKey, select, func, delete, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from passlib.context import CryptContext
from jose import jwt

BASE=Path(__file__).resolve().parent.parent
FRONT=BASE/'frontend'; UP=BASE/'uploads'/'products'; DB=BASE/'database'
UP.mkdir(parents=True,exist_ok=True); DB.mkdir(parents=True,exist_ok=True)
URL=os.getenv('DATABASE_URL',f"sqlite:///{DB/'bananos_pos.db'}")
SECRET=os.getenv('SECRET_KEY','bananos-dev-change-this-in-production')
engine=create_engine(URL,connect_args={'check_same_thread':False} if URL.startswith('sqlite') else {})
pwd=CryptContext(schemes=['bcrypt'],deprecated='auto'); bearer=HTTPBearer(auto_error=False)

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'; id:Mapped[int]=mapped_column(primary_key=True); username:Mapped[str]=mapped_column(String(50),unique=True); password_hash:Mapped[str]=mapped_column(String(255)); role:Mapped[str]=mapped_column(String(20)); active:Mapped[bool]=mapped_column(Boolean,default=True)
class Product(Base):
    __tablename__='products'; id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(100)); description:Mapped[str]=mapped_column(String(400),default=''); category:Mapped[str]=mapped_column(String(60)); price:Mapped[float]=mapped_column(Float); stock:Mapped[int]=mapped_column(Integer,default=0); min_stock:Mapped[int]=mapped_column(Integer,default=5); image:Mapped[str]=mapped_column(String(255),default=''); active:Mapped[bool]=mapped_column(Boolean,default=True); beer_selectable:Mapped[bool]=mapped_column(Boolean,default=False)
class Sale(Base):
    __tablename__='sales'; id:Mapped[int]=mapped_column(primary_key=True); seller_id:Mapped[int]=mapped_column(ForeignKey('users.id')); total:Mapped[float]=mapped_column(Float); payment_method:Mapped[str]=mapped_column(String(30)); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.now)
class SaleItem(Base):
    __tablename__='sale_items'; id:Mapped[int]=mapped_column(primary_key=True); sale_id:Mapped[int]=mapped_column(ForeignKey('sales.id')); product_id:Mapped[int]=mapped_column(ForeignKey('products.id')); product_name:Mapped[str]=mapped_column(String(100)); qty:Mapped[int]=mapped_column(Integer); unit_price:Mapped[float]=mapped_column(Float); beer_type:Mapped[str]=mapped_column(String(60),default='')
class CashSession(Base):
    __tablename__='cash_sessions'; id:Mapped[int]=mapped_column(primary_key=True); seller_id:Mapped[int]=mapped_column(ForeignKey('users.id')); opening_amount:Mapped[float]=mapped_column(Float); closing_amount:Mapped[float|None]=mapped_column(Float,nullable=True); opened_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.now); closed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
class Preparation(Base):
    __tablename__='preparations'; id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(60),unique=True); extra_price:Mapped[float]=mapped_column(Float,default=0); active:Mapped[bool]=mapped_column(Boolean,default=True); sort_order:Mapped[int]=mapped_column(Integer,default=0)
class TableAccount(Base):
    __tablename__='table_accounts'; id:Mapped[int]=mapped_column(primary_key=True); table_number:Mapped[int]=mapped_column(Integer,unique=True); items_json:Mapped[str]=mapped_column(String,default='[]'); updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.now)
Base.metadata.create_all(engine)

import json
with Session(engine) as _s:
    if not _s.scalar(select(func.count(Preparation.id))):
        _s.add_all([Preparation(name='Normal',extra_price=0,sort_order=0),Preparation(name='Escarchada',extra_price=10,sort_order=1),Preparation(name='Chelada',extra_price=15,sort_order=2),Preparation(name='Michelada',extra_price=25,sort_order=3)])
    for _n in range(1,11):
        if not _s.scalar(select(TableAccount).where(TableAccount.table_number==_n)):
            _s.add(TableAccount(table_number=_n,items_json='[]'))
    _s.commit()

def db():
    with Session(engine) as s: yield s

def current_user(c:HTTPAuthorizationCredentials=Depends(bearer),s:Session=Depends(db)):
    if not c: raise HTTPException(401,'Sesión requerida')
    try: uid=int(jwt.decode(c.credentials,SECRET,algorithms=['HS256'])['sub'])
    except Exception: raise HTTPException(401,'Sesión inválida')
    u=s.get(User,uid)
    if not u or not u.active: raise HTTPException(401,'Usuario inválido')
    return u

def admin(u=Depends(current_user)):
    if u.role!='admin': raise HTTPException(403,'Solo administrador')
    return u

with Session(engine) as s:
    if not s.scalar(select(func.count(User.id))):
        s.add_all([User(username='admin',password_hash=pwd.hash('admin123'),role='admin'),User(username='vendedor',password_hash=pwd.hash('venta123'),role='seller')])
    if not s.scalar(select(func.count(Product.id))):
        seed=[('MICHELADA','CERVEZAS',80,48,True,'Michelada preparada al estilo BANANOS'),('CHELADA','CERVEZAS',65,48,True,'Cerveza fría preparada con limón y sal'),('PALOMA','TEQUILA',75,20,False,'Toronja, tequila y hielo'),('VAMPIRO','TEQUILA',80,15,False,'Tequila y mezcla preparada'),('MOJITO','RON',75,18,False,'Ron, hierbabuena y limón'),('PIÑA COLADA','RON',85,12,False,'Piña, coco y ron'),('MARUCHAN','SNACKS',45,20,False,'Sopa preparada'),('PALOMITAS','SNACKS',35,25,False,'Botana para compartir')]
        for n,c,p,st,b,d in seed:s.add(Product(name=n,category=c,price=p,stock=st,beer_selectable=b,description=d))
    s.commit()

app=FastAPI(title='BANANOS MANAGER',version='3.0')
app.mount('/static',StaticFiles(directory=FRONT),name='static'); app.mount('/uploads',StaticFiles(directory=BASE/'uploads'),name='uploads')
@app.get('/')
def home(): return FileResponse(FRONT/'index.html')
@app.get('/app')
def ui(): return FileResponse(FRONT/'app.html')
@app.get('/api/status')
def status(): return {'ok':True,'name':'BANANOS MANAGER','version':'3.0'}
@app.post('/api/login')
async def login(r:Request,s:Session=Depends(db)):
    b=await r.json(); u=s.scalar(select(User).where(User.username==b.get('username','')))
    if not u or not u.active or not pwd.verify(b.get('password',''),u.password_hash): raise HTTPException(401,'Credenciales incorrectas')
    token=jwt.encode({'sub':str(u.id),'exp':datetime.utcnow()+timedelta(hours=12)},SECRET,algorithm='HS256')
    return {'token':token,'role':u.role,'username':u.username}
@app.get('/api/me')
def me(u=Depends(current_user)): return {'id':u.id,'username':u.username,'role':u.role}
@app.patch('/api/me')
async def update_my_account(r:Request,u=Depends(admin),s:Session=Depends(db)):
    b=await r.json()
    username=str(b.get('username','')).strip()
    current_password=str(b.get('current_password',''))
    new_password=str(b.get('new_password',''))
    if not current_password or not pwd.verify(current_password,u.password_hash):
        raise HTTPException(400,'La contraseña actual es incorrecta')
    if username:
        if len(username)<3: raise HTTPException(400,'El usuario debe tener al menos 3 caracteres')
        exists=s.scalar(select(User).where(User.username==username,User.id!=u.id))
        if exists: raise HTTPException(400,'Ese nombre de usuario ya está en uso')
        u.username=username
    if new_password:
        if len(new_password)<6: raise HTTPException(400,'La nueva contraseña debe tener al menos 6 caracteres')
        u.password_hash=pwd.hash(new_password)
    s.commit();s.refresh(u)
    return {'ok':True,'username':u.username,'role':u.role}

@app.post('/api/admin/verify-password')
async def verify_admin_password(r:Request,u=Depends(admin),s:Session=Depends(db)):
    b=await r.json()
    password=str(b.get('password',''))
    if not password or not pwd.verify(password,u.password_hash):
        raise HTTPException(400,'Contraseña incorrecta')
    return {'ok':True}

@app.post('/api/admin/reset-history')
async def reset_history(r:Request,u=Depends(admin),s:Session=Depends(db)):
    b=await r.json()
    password=str(b.get('password',''))
    confirmation=str(b.get('confirmation','')).strip().upper()
    if not password or not pwd.verify(password,u.password_hash):
        raise HTTPException(400,'La contraseña del administrador es incorrecta')
    if confirmation!='BORRAR TODO':
        raise HTTPException(400,'Escribe BORRAR TODO para confirmar')
    # Borra únicamente información operativa/histórica. Conserva usuarios, productos, stock y extras.
    s.execute(delete(SaleItem))
    s.execute(delete(Sale))
    s.execute(delete(CashSession))
    for table in s.scalars(select(TableAccount)).all():
        table.items_json='[]'
        table.updated_at=datetime.now()
    # Reinicia consecutivos en SQLite para que el historial nuevo comience desde 1.
    if URL.startswith('sqlite'):
        try:
            s.execute(text("DELETE FROM sqlite_sequence WHERE name IN ('sale_items','sales','cash_sessions')"))
        except Exception:
            pass
    s.commit()
    return {'ok':True,'message':'Historial eliminado. BANANOS MANAGER está listo para comenzar un nuevo registro.'}
@app.get('/api/products')
def products(u=Depends(current_user),s:Session=Depends(db)):
    ps=s.scalars(select(Product).where(Product.active==True).order_by(Product.category,Product.name)).all()
    return [{'id':p.id,'name':p.name,'description':p.description,'category':p.category,'price':p.price,'stock':p.stock if u.role=='admin' else None,'min_stock':p.min_stock if u.role=='admin' else None,'image':p.image,'beer_selectable':p.beer_selectable,'preparations_enabled':p.beer_selectable} for p in ps]
@app.post('/api/products')
async def add_product(name:str=Form(...),category:str=Form(...),price:float=Form(...),stock:int=Form(0),min_stock:int=Form(5),description:str=Form(''),beer_selectable:bool=Form(False),image:UploadFile|None=File(None),u=Depends(admin),s:Session=Depends(db)):
    image_url=''
    if image and image.filename:
        ext=Path(image.filename).suffix.lower()
        if ext not in {'.jpg','.jpeg','.png','.webp'}: raise HTTPException(400,'Formato de imagen inválido')
        fn=uuid.uuid4().hex+ext; (UP/fn).write_bytes(await image.read()); image_url='/uploads/products/'+fn
    p=Product(name=name.strip(),category=category.strip().upper(),price=price,stock=stock,min_stock=min_stock,description=description.strip(),beer_selectable=beer_selectable,image=image_url); s.add(p);s.commit();s.refresh(p);return {'ok':True,'id':p.id}
@app.patch('/api/products/{pid}')
async def edit_product(pid:int,r:Request,u=Depends(admin),s:Session=Depends(db)):
    p=s.get(Product,pid)
    if not p or not p.active: raise HTTPException(404,'Producto no encontrado')
    b=await r.json()
    for k in ('name','category','price','stock','min_stock','description','beer_selectable'):
        if k in b:setattr(p,k,b[k])
    if 'category' in b:p.category=str(p.category).upper()
    s.commit();return {'ok':True}
@app.post('/api/products/{pid}/image')
async def product_image(pid:int,image:UploadFile=File(...),u=Depends(admin),s:Session=Depends(db)):
    p=s.get(Product,pid)
    if not p:raise HTTPException(404,'Producto no encontrado')
    ext=Path(image.filename or '').suffix.lower()
    if ext not in {'.jpg','.jpeg','.png','.webp'}:raise HTTPException(400,'Formato inválido')
    fn=uuid.uuid4().hex+ext;(UP/fn).write_bytes(await image.read());p.image='/uploads/products/'+fn;s.commit();return {'ok':True,'image':p.image}
@app.delete('/api/products/{pid}')
def remove_product(pid:int,u=Depends(admin),s:Session=Depends(db)):
    p=s.get(Product,pid)
    if not p:raise HTTPException(404,'Producto no encontrado')
    p.active=False;s.commit();return {'ok':True}
@app.get('/api/preparations')
def preparations(u=Depends(current_user),s:Session=Depends(db)):
    rows=s.scalars(select(Preparation).where(Preparation.active==True).order_by(Preparation.sort_order,Preparation.id)).all()
    return [{'id':x.id,'name':x.name,'extra_price':x.extra_price,'active':x.active} for x in rows]
@app.patch('/api/preparations/{prep_id}')
async def edit_preparation(prep_id:int,r:Request,u=Depends(admin),s:Session=Depends(db)):
    x=s.get(Preparation,prep_id)
    if not x: raise HTTPException(404,'Preparación no encontrada')
    b=await r.json()
    if 'name' in b: x.name=str(b['name']).strip()
    if 'extra_price' in b: x.extra_price=max(0,float(b['extra_price']))
    s.commit();return {'ok':True}
@app.post('/api/preparations')
async def add_preparation(r:Request,u=Depends(admin),s:Session=Depends(db)):
    b=await r.json();name=str(b.get('name','')).strip();price=max(0,float(b.get('extra_price',0)))
    if not name: raise HTTPException(400,'Nombre requerido')
    if s.scalar(select(Preparation).where(Preparation.name==name)): raise HTTPException(400,'Ya existe')
    x=Preparation(name=name,extra_price=price,sort_order=99);s.add(x);s.commit();return {'ok':True}
@app.post('/api/sales')
async def create_sale(r:Request,u=Depends(current_user),s:Session=Depends(db)):
    if u.role=='seller' and not s.scalar(select(CashSession).where(CashSession.seller_id==u.id,CashSession.closed_at==None)):
        raise HTTPException(403,'Debes abrir la caja antes de realizar ventas')
    b=await r.json(); rows=[]; total=0.0
    for x in b.get('items',[]):
        p=s.get(Product,int(x['product_id']));q=int(x['qty']);prep=str(x.get('preparation',x.get('beer_type',''))).strip()
        if not p or not p.active:raise HTTPException(400,'Producto no disponible')
        if q<1:raise HTTPException(400,'Cantidad inválida')
        if p.stock<q:raise HTTPException(400,f'Stock insuficiente: {p.name}')
        extra=0.0
        if p.beer_selectable:
            if not prep: prep='Normal'
            pr=s.scalar(select(Preparation).where(Preparation.name==prep,Preparation.active==True))
            if not pr: raise HTTPException(400,f'Preparación inválida para {p.name}')
            extra=pr.extra_price
        else: prep=''
        unit=round(p.price+extra,2);rows.append((p,q,prep,unit));total+=unit*q
    if not rows:raise HTTPException(400,'Carrito vacío')
    sale=Sale(seller_id=u.id,total=round(total,2),payment_method=b.get('payment_method','cash'));s.add(sale);s.flush()
    for p,q,prep,unit in rows:
        p.stock-=q;s.add(SaleItem(sale_id=sale.id,product_id=p.id,product_name=p.name,qty=q,unit_price=unit,beer_type=prep))
    s.commit();return {'ok':True,'id':sale.id,'total':sale.total}
@app.get('/api/dashboard')
def dashboard(u=Depends(admin),s:Session=Depends(db)):
    now=datetime.now(); today=now.replace(hour=0,minute=0,second=0,microsecond=0); yesterday=today-timedelta(days=1)
    sales=s.scalars(select(Sale).where(Sale.created_at>=today)).all(); ys=s.scalars(select(Sale).where(Sale.created_at>=yesterday,Sale.created_at<today)).all()
    items=s.scalars(select(SaleItem)).all(); counts={}
    for i in items: counts[i.product_name]=counts.get(i.product_name,0)+i.qty
    products=s.scalars(select(Product).where(Product.active==True)).all(); low=[{'name':p.name,'stock':p.stock,'min':p.min_stock,'missing':max(0,p.min_stock-p.stock)} for p in products if p.stock<=p.min_stock]
    ordered=sorted(counts.items(),key=lambda x:x[1],reverse=True); chart=[]
    for offset in range(6,-1,-1):
        start=today-timedelta(days=offset); end=start+timedelta(days=1); ds=s.scalars(select(Sale).where(Sale.created_at>=start,Sale.created_at<end)).all()
        chart.append({'label':start.strftime('%d/%m'),'total':round(sum(v.total for v in ds),2),'tickets':len(ds)})
    payment={'cash':0.0,'card':0.0,'transfer':0.0}
    for v in sales: payment[v.payment_method]=round(payment.get(v.payment_method,0)+v.total,2)
    seller_rows=s.execute(select(User.username,func.coalesce(func.sum(Sale.total),0),func.count(Sale.id)).join(Sale,Sale.seller_id==User.id).where(Sale.created_at>=today).group_by(User.id).order_by(func.sum(Sale.total).desc())).all()
    open_cash=s.scalar(select(func.count(CashSession.id)).where(CashSession.closed_at==None)) or 0
    total=round(sum(x.total for x in sales),2); ytotal=round(sum(x.total for x in ys),2)
    change=round(((total-ytotal)/ytotal)*100,1) if ytotal else (100.0 if total else 0.0)
    all_sales=s.scalars(select(Sale)).all()
    all_total=round(sum(x.total for x in all_sales),2)
    inventory_units=sum(p.stock for p in products)
    inventory_value=round(sum(p.stock*p.price for p in products),2)
    return {'total':total,'all_total':all_total,'tickets':len(sales),'avg':round(total/len(sales),2) if sales else 0,'yesterday_total':ytotal,'change_pct':change,'top':ordered[:5],'bottom':list(reversed(ordered[-5:])) if ordered else [],'low':low,'healthy':len([p for p in products if p.stock>p.min_stock]),'products':len(products),'inventory_units':inventory_units,'inventory_value':inventory_value,'chart':chart,'sellers':[{'name':r[0],'total':round(float(r[1]),2),'tickets':r[2]} for r in seller_rows]}
@app.get('/api/sales')
def sales(u=Depends(admin),s:Session=Depends(db)):
    rows=s.execute(select(Sale,User.username).join(User,Sale.seller_id==User.id).order_by(Sale.id.desc()).limit(150)).all()
    out=[]
    for v,name in rows:
        its=s.scalars(select(SaleItem).where(SaleItem.sale_id==v.id)).all()
        out.append({'id':v.id,'total':v.total,'date':v.created_at.isoformat(),'seller':name,'items':[{'name':i.product_name,'qty':i.qty,'unit_price':i.unit_price,'preparation':i.beer_type,'subtotal':round(i.qty*i.unit_price,2)} for i in its]})
    return out

@app.get('/api/report/pdf')
def report_pdf(u=Depends(admin),s:Session=Depends(db)):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from fastapi.responses import StreamingResponse
    products=s.scalars(select(Product).where(Product.active==True).order_by(Product.category,Product.name)).all()
    now=datetime.now();buf=BytesIO();doc=SimpleDocTemplate(buf,pagesize=letter,rightMargin=32,leftMargin=32,topMargin=34,bottomMargin=34)
    styles=getSampleStyleSheet(); title=ParagraphStyle('Title',parent=styles['Title'],alignment=TA_CENTER,fontSize=20,leading=24,spaceAfter=4)
    sub=ParagraphStyle('Sub',parent=styles['Normal'],alignment=TA_CENTER,fontSize=9,textColor=colors.HexColor('#666666'),spaceAfter=18)
    story=[Paragraph('BANANOS MANAGER',title),Paragraph('REPORTE DE STOCK',styles['Heading2']),Paragraph('Generado: '+now.strftime('%d/%m/%Y %H:%M'),sub)]
    data=[['PRODUCTO','CATEGORÍA','STOCK']]
    for p in products:data.append([p.name,p.category,str(p.stock)])
    table=Table(data,colWidths=[260,170,70],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F4C900')),('TEXTCOLOR',(0,0),(-1,0),colors.black),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),9),('ALIGN',(-1,1),(-1,-1),'CENTER'),('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#CCCCCC')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F7F7F7')]),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story += [table,Spacer(1,12),Paragraph(f'Productos registrados: {len(products)} · Unidades totales: {sum(p.stock for p in products)}',styles['Normal'])]
    doc.build(story);buf.seek(0);filename='bananos_stock_'+now.strftime('%Y%m%d_%H%M')+'.pdf'
    return StreamingResponse(buf,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{filename}"'})

@app.get('/api/users')
def list_users(u=Depends(admin),s:Session=Depends(db)):
    rows=s.scalars(select(User).where(User.role=='seller').order_by(User.username)).all()
    return [{'id':x.id,'username':x.username,'active':x.active} for x in rows]

@app.post('/api/users')
async def create_user(r:Request,u=Depends(admin),s:Session=Depends(db)):
    b=await r.json(); username=str(b.get('username','')).strip(); password=str(b.get('password',''))
    if len(username)<3: raise HTTPException(400,'El usuario debe tener al menos 3 caracteres')
    if len(password)<6: raise HTTPException(400,'La contraseña debe tener al menos 6 caracteres')
    if s.scalar(select(User).where(User.username==username)): raise HTTPException(400,'Ese usuario ya existe')
    x=User(username=username,password_hash=pwd.hash(password),role='seller',active=True);s.add(x);s.commit();s.refresh(x)
    return {'ok':True,'id':x.id}

@app.patch('/api/users/{uid}')
async def edit_user(uid:int,r:Request,u=Depends(admin),s:Session=Depends(db)):
    x=s.get(User,uid)
    if not x or x.role!='seller': raise HTTPException(404,'Vendedor no encontrado')
    b=await r.json()
    if 'active' in b: x.active=bool(b['active'])
    if b.get('password'):
        password=str(b['password'])
        if len(password)<6: raise HTTPException(400,'La contraseña debe tener al menos 6 caracteres')
        x.password_hash=pwd.hash(password)
    s.commit();return {'ok':True}

@app.get('/api/cash/history')
def cash_history(u=Depends(admin),s:Session=Depends(db)):
    rows=s.execute(select(CashSession,User.username).join(User,CashSession.seller_id==User.id).order_by(CashSession.id.desc()).limit(300)).all(); out=[]
    for c,name in rows:
        end=c.closed_at or datetime.now(); sales=s.scalars(select(Sale).where(Sale.seller_id==c.seller_id,Sale.created_at>=c.opened_at,Sale.created_at<=end)).all()
        out.append({'id':c.id,'seller':name,'opened_at':c.opened_at.isoformat(),'closed_at':c.closed_at.isoformat() if c.closed_at else None,'sales_total':round(sum(v.total for v in sales),2),'tickets':len(sales)})
    return out

@app.get('/api/cash')
def cash(u=Depends(current_user),s:Session=Depends(db)):
    now=datetime.now(); today=now.replace(hour=0,minute=0,second=0,microsecond=0)
    c=s.scalar(select(CashSession).where(CashSession.seller_id==u.id,CashSession.closed_at==None).order_by(CashSession.id.desc()))
    day_sales=s.scalars(select(Sale).where(Sale.seller_id==u.id,Sale.created_at>=today).order_by(Sale.id.desc())).all()
    session_sales=[]
    if c: session_sales=s.scalars(select(Sale).where(Sale.seller_id==u.id,Sale.created_at>=c.opened_at).order_by(Sale.id.desc())).all()
    return {'open':bool(c),'opened_at':c.opened_at.isoformat() if c else None,'session_total':round(sum(v.total for v in session_sales),2),'session_tickets':len(session_sales),'day_total':round(sum(v.total for v in day_sales),2),'day_tickets':len(day_sales),'history':[{'id':v.id,'total':v.total,'payment':v.payment_method,'date':v.created_at.isoformat()} for v in day_sales]}

@app.post('/api/cash/open')
async def open_cash(r:Request,u=Depends(current_user),s:Session=Depends(db)):
    existing=s.scalar(select(CashSession).where(CashSession.seller_id==u.id,CashSession.closed_at==None))
    if existing: raise HTTPException(400,'Ya tienes una caja abierta')
    c=CashSession(seller_id=u.id,opening_amount=0); s.add(c); s.commit(); s.refresh(c)
    return {'ok':True,'opened_at':c.opened_at.isoformat()}

@app.post('/api/cash/close')
async def close_cash(r:Request,u=Depends(current_user),s:Session=Depends(db)):
    c=s.scalar(select(CashSession).where(CashSession.seller_id==u.id,CashSession.closed_at==None).order_by(CashSession.id.desc()))
    if not c: raise HTTPException(400,'No hay caja abierta')
    end=datetime.now(); sales=s.scalars(select(Sale).where(Sale.seller_id==u.id,Sale.created_at>=c.opened_at,Sale.created_at<=end)).all()
    c.closing_amount=round(sum(v.total for v in sales),2); c.closed_at=end; s.commit()
    today=end.replace(hour=0,minute=0,second=0,microsecond=0); day_sales=s.scalars(select(Sale).where(Sale.seller_id==u.id,Sale.created_at>=today,Sale.created_at<=end).order_by(Sale.id.desc())).all()
    return {'ok':True,'closed_at':end.isoformat(),'session_total':c.closing_amount,'session_tickets':len(sales),'day_total':round(sum(v.total for v in day_sales),2),'day_tickets':len(day_sales),'history':[{'id':v.id,'total':v.total,'payment':v.payment_method,'date':v.created_at.isoformat()} for v in day_sales]}


@app.get('/api/tables')
def tables(u=Depends(current_user),s:Session=Depends(db)):
    out=[]
    for t in s.scalars(select(TableAccount).order_by(TableAccount.table_number)).all():
        items=json.loads(t.items_json or '[]'); total=sum(float(x['price'])*int(x['qty']) for x in items)
        out.append({'table':t.table_number,'items':items,'count':sum(int(x['qty']) for x in items),'total':round(total,2),'open':bool(items),'updated_at':t.updated_at.isoformat()})
    return out

@app.put('/api/tables/{number}')
async def save_table(number:int,r:Request,u=Depends(current_user),s:Session=Depends(db)):
    if u.role=='seller' and not s.scalar(select(CashSession).where(CashSession.seller_id==u.id,CashSession.closed_at==None)):
        raise HTTPException(403,'Debes abrir la caja antes de usar mesas')
    if number<1 or number>10: raise HTTPException(400,'Mesa inválida')
    b=await r.json(); clean=[]
    for x in b.get('items',[]):
        p=s.get(Product,int(x['product_id'])); q=int(x['qty']); prep=str(x.get('preparation',x.get('beer_type',''))).strip()
        if not p or not p.active or q<1: raise HTTPException(400,'Producto inválido')
        extra=0.0
        if p.beer_selectable:
            if not prep: prep='Normal'
            pr=s.scalar(select(Preparation).where(Preparation.name==prep,Preparation.active==True))
            if not pr: raise HTTPException(400,f'Preparación inválida para {p.name}')
            extra=pr.extra_price
        else: prep=''
        clean.append({'product_id':p.id,'name':p.name,'price':round(p.price+extra,2),'base_price':p.price,'qty':q,'beer_type':prep,'preparation':prep})
    t=s.scalar(select(TableAccount).where(TableAccount.table_number==number)); t.items_json=json.dumps(clean,ensure_ascii=False);t.updated_at=datetime.now();s.commit()
    return {'ok':True}

@app.post('/api/tables/{number}/checkout')
async def checkout_table(number:int,r:Request,u=Depends(current_user),s:Session=Depends(db)):
    if u.role=='seller' and not s.scalar(select(CashSession).where(CashSession.seller_id==u.id,CashSession.closed_at==None)):
        raise HTTPException(403,'Debes abrir la caja antes de cobrar mesas')
    t=s.scalar(select(TableAccount).where(TableAccount.table_number==number))
    if not t: raise HTTPException(404,'Mesa no encontrada')
    items=json.loads(t.items_json or '[]')
    if not items: raise HTTPException(400,'La mesa no tiene cuenta')
    total=0.0; rows=[]
    for x in items:
        p=s.get(Product,int(x['product_id'])); q=int(x['qty']); prep=str(x.get('preparation',x.get('beer_type','')))
        if not p or not p.active or p.stock<q: raise HTTPException(400,f"Stock insuficiente: {x['name']}")
        unit=float(x.get('price',p.price)); total+=unit*q; rows.append((p,q,prep,unit))
    b=await r.json(); sale=Sale(seller_id=u.id,total=round(total,2),payment_method=b.get('payment_method','cash'));s.add(sale);s.flush()
    for p,q,prep,unit in rows:
        p.stock-=q;s.add(SaleItem(sale_id=sale.id,product_id=p.id,product_name=p.name,qty=q,unit_price=unit,beer_type=prep))
    t.items_json='[]';t.updated_at=datetime.now();s.commit()
    return {'ok':True,'id':sale.id,'total':sale.total}
