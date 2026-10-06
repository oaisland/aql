import csv, io, os, secrets
from datetime import date, datetime
from functools import wraps
from flask import Flask, Response, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash
from aql import AQL_VALUES, LEVELS, calculate

app=Flask(__name__)
app.config["SECRET_KEY"]=os.environ.get("SECRET_KEY", "")
if not app.config["SECRET_KEY"]: raise RuntimeError("必须设置 SECRET_KEY 环境变量")
data_dir=os.environ.get("DATA_DIR","/data")
os.makedirs(data_dir,exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"]="sqlite:///"+os.path.join(data_dir,"aql.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"]=False
app.config["SQLALCHEMY_ENGINE_OPTIONS"]={"connect_args":{"timeout":30}}
app.config["SESSION_COOKIE_HTTPONLY"]=True
app.config["SESSION_COOKIE_SAMESITE"]="Lax"
app.config["SESSION_COOKIE_SECURE"]=os.environ.get("COOKIE_SECURE","0")=="1"
db=SQLAlchemy(app)

class User(db.Model):
    __tablename__="users"
    id=db.Column(db.Integer,primary_key=True); username=db.Column(db.String(80),unique=True,nullable=False)
    password_hash=db.Column(db.String(255),nullable=False); role=db.Column(db.String(20),nullable=False,default="inspector")
    active=db.Column(db.Boolean,nullable=False,default=True)
class Inspection(db.Model):
    __tablename__="inspections"
    id=db.Column(db.Integer,primary_key=True); order_no=db.Column(db.String(100),nullable=False,index=True)
    product=db.Column(db.String(200),nullable=False,index=True); sku=db.Column(db.String(100),default="")
    factory=db.Column(db.String(200),default="",index=True); lot_size=db.Column(db.Integer,nullable=False); level=db.Column(db.String(5),nullable=False)
    aql_cri=db.Column(db.String(10),nullable=False); aql_maj=db.Column(db.String(10),nullable=False); aql_min=db.Column(db.String(10),nullable=False)
    code_letter=db.Column(db.String(10),nullable=False); sample_size=db.Column(db.Integer,nullable=False)
    ac_cri=db.Column(db.Integer,nullable=False); re_cri=db.Column(db.Integer,nullable=False)
    ac_maj=db.Column(db.Integer,nullable=False); re_maj=db.Column(db.Integer,nullable=False)
    ac_min=db.Column(db.Integer,nullable=False); re_min=db.Column(db.Integer,nullable=False)
    inspect_date=db.Column(db.Date,nullable=False,default=date.today); inspector=db.Column(db.String(80),nullable=False)
    verdict=db.Column(db.String(20),nullable=False,default="待检"); created_by=db.Column(db.Integer,db.ForeignKey("users.id"),nullable=False,index=True)
    created_at=db.Column(db.DateTime,nullable=False,default=datetime.utcnow)
    defects=db.relationship("Defect",backref="inspection",cascade="all, delete-orphan",lazy=True)
class Defect(db.Model):
    __tablename__="defects"
    id=db.Column(db.Integer,primary_key=True); inspection_id=db.Column(db.Integer,db.ForeignKey("inspections.id"),nullable=False,index=True)
    category=db.Column(db.String(3),nullable=False); description=db.Column(db.String(500),nullable=False); qty=db.Column(db.Integer,nullable=False,default=1)

def init_db():
    db.create_all()
    u = os.getenv("ADMIN_USER")
    p = os.getenv("ADMIN_PASSWORD")
    if u and p:
        # 增加查询判断：只有当用户名不存在时才创建
        existing_user = User.query.filter_by(username=u).first()
        if not existing_user:
            db.session.add(User(
                username=u,
                password_hash=generate_password_hash(p),
                role="admin",
                active=True
            ))
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
with app.app_context(): init_db()

def current_user(): return db.session.get(User,session.get("uid")) if session.get("uid") else None
@app.context_processor
def ctx(): return {"me":current_user(),"AQL_VALUES":AQL_VALUES,"LEVELS":LEVELS,"csrf_token":lambda:session.setdefault("csrf",secrets.token_hex(24))}
@app.before_request
def csrf_guard():
    if request.method in ("POST","PUT","PATCH","DELETE"):
        token=request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not secrets.compare_digest(token,session.get("csrf","")): abort(400,"CSRF 校验失败")
def login_required(fn):
    @wraps(fn)
    def inner(*a,**kw):
        u=current_user()
        if not u or not u.active: session.clear(); return redirect(url_for("login"))
        return fn(*a,**kw)
    return inner
def admin_required(fn):
    @wraps(fn)
    def inner(*a,**kw):
        u=current_user()
        if not u or u.role!="admin": abort(403)
        return fn(*a,**kw)
    return inner
def owned_or_404(i):
    u=current_user()
    if not i or (u.role!="admin" and i.created_by!=u.id): abort(404)
    return i

def totals(i):
    out={"CRI":0,"MAJ":0,"MIN":0}
    for d in i.defects: out[d.category]+=d.qty
    return out
def refresh_verdict(i):
    t=totals(i)
    i.verdict="不合格" if t["CRI"]>=i.re_cri or t["MAJ"]>=i.re_maj or t["MIN"]>=i.re_min else "合格"

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=User.query.filter_by(username=request.form.get("username","").strip()).first()
        if u and u.active and check_password_hash(u.password_hash,request.form.get("password","")):
            session.clear(); session["uid"]=u.id; session["csrf"]=secrets.token_hex(24); return redirect(url_for("index"))
        flash("用户名或密码错误，或账号已禁用","error")
    return render_template("login.html")
@app.post("/logout")
@login_required
def logout(): session.clear(); return redirect(url_for("login"))

def filtered_inspections():
    u=current_user(); q=Inspection.query
    if u.role!="admin": q=q.filter_by(created_by=u.id)
    keyword=request.args.get("q","").strip(); start=request.args.get("start",""); end=request.args.get("end","")
    if keyword:
        like=f"%{keyword}%"; q=q.filter(or_(Inspection.order_no.ilike(like),Inspection.product.ilike(like),Inspection.sku.ilike(like),Inspection.factory.ilike(like)))
    try:
        if start:q=q.filter(Inspection.inspect_date>=date.fromisoformat(start))
        if end:q=q.filter(Inspection.inspect_date<=date.fromisoformat(end))
    except ValueError: flash("日期格式无效","error")
    return q,keyword,start,end

@app.get("/")
@login_required
def index():
    q,keyword,start,end=filtered_inspections()
    return render_template("index.html",items=q.order_by(Inspection.created_at.desc()).all(),q=keyword,start=start,end=end)

@app.get("/api/plan")
@login_required
def api_plan():
    try: return jsonify(calculate(request.args["lot_size"],request.args.get("level","II"),request.args.get("aql_cri","0.010"),request.args.get("aql_maj","1.5"),request.args.get("aql_min","4.0")))
    except (ValueError,KeyError) as e: return jsonify({"error":str(e)}),400

def apply_form(i):
    i.order_no=request.form.get("order_no","").strip(); i.product=request.form.get("product","").strip(); i.sku=request.form.get("sku","").strip(); i.factory=request.form.get("factory","").strip()
    if not i.order_no or not i.product: raise ValueError("订单号和产品名称不能为空")
    i.lot_size=int(request.form["lot_size"]); i.level=request.form["level"]; i.aql_cri=request.form["aql_cri"]; i.aql_maj=request.form["aql_maj"]; i.aql_min=request.form["aql_min"]
    plan=calculate(i.lot_size,i.level,i.aql_cri,i.aql_maj,i.aql_min); i.code_letter=plan["code_letter"]; i.sample_size=plan["sample_size"]
    for k in ("cri","maj","min"):
        setattr(i,"ac_"+k,plan["criteria"][k]["ac"]); setattr(i,"re_"+k,plan["criteria"][k]["re"])
    i.inspect_date=date.fromisoformat(request.form["inspect_date"]); i.inspector=request.form.get("inspector","").strip() or current_user().username

@app.route("/inspections/new",methods=["GET","POST"])
@login_required
def inspection_new():
    if request.method=="POST":
        try:
            i=Inspection(created_by=current_user().id); apply_form(i); db.session.add(i); refresh_verdict(i); db.session.commit(); flash("检验单已创建","ok"); return redirect(url_for("inspection_detail",iid=i.id))
        except (ValueError,KeyError) as e: db.session.rollback(); flash(str(e),"error")
    return render_template("inspection_form.html",item=None,today=date.today().isoformat())
@app.route("/inspections/<int:iid>/edit",methods=["GET","POST"])
@login_required
def inspection_edit(iid):
    i=owned_or_404(db.session.get(Inspection,iid))
    if request.method=="POST":
        try: apply_form(i); refresh_verdict(i); db.session.commit(); flash("检验单已更新","ok"); return redirect(url_for("inspection_detail",iid=i.id))
        except (ValueError,KeyError) as e: db.session.rollback(); flash(str(e),"error")
    return render_template("inspection_form.html",item=i,today=date.today().isoformat())
@app.get("/inspections/<int:iid>")
@login_required
def inspection_detail(iid):
    i=owned_or_404(db.session.get(Inspection,iid)); return render_template("inspection_detail.html",item=i,totals=totals(i))
@app.post("/inspections/<int:iid>/delete")
@login_required
def inspection_delete(iid):
    i=owned_or_404(db.session.get(Inspection,iid)); db.session.delete(i); db.session.commit(); flash("检验单已删除","ok"); return redirect(url_for("index"))
@app.post("/inspections/<int:iid>/defects")
@login_required
def defect_add(iid):
    i=owned_or_404(db.session.get(Inspection,iid)); cat=request.form.get("category")
    if cat not in ("CRI","MAJ","MIN"): abort(400)
    desc=request.form.get("description","").strip(); qty=int(request.form.get("qty",0))
    if not desc or qty<1: flash("请输入缺陷描述和大于 0 的数量","error")
    else: db.session.add(Defect(inspection=i,category=cat,description=desc,qty=qty)); db.session.flush(); refresh_verdict(i); db.session.commit(); flash("缺陷已添加","ok")
    return redirect(url_for("inspection_detail",iid=i.id))
@app.post("/defects/<int:did>/delete")
@login_required
def defect_delete(did):
    d=db.session.get(Defect,did); i=owned_or_404(d.inspection if d else None); db.session.delete(d); db.session.flush(); refresh_verdict(i); db.session.commit(); return redirect(url_for("inspection_detail",iid=i.id))
@app.get("/inspections/<int:iid>/report")
@login_required
def report(iid):
    i=owned_or_404(db.session.get(Inspection,iid)); return render_template("report.html",item=i,totals=totals(i))
@app.get("/export.csv")
@login_required
def export_csv():
    q,_,_,_=filtered_inspections()
    s=io.StringIO(); s.write("\ufeff"); w=csv.writer(s); w.writerow(["订单号","产品","SKU","工厂","批量","水平","样本量","CRI Ac/Re","MAJ Ac/Re","MIN Ac/Re","日期","检验员","判定"])
    for i in q.order_by(Inspection.inspect_date.desc()): w.writerow([i.order_no,i.product,i.sku,i.factory,i.lot_size,i.level,i.sample_size,f"{i.ac_cri}/{i.re_cri}",f"{i.ac_maj}/{i.re_maj}",f"{i.ac_min}/{i.re_min}",i.inspect_date,i.inspector,i.verdict])
    return Response(s.getvalue(),mimetype="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=inspections.csv"})

@app.get("/users")
@login_required
@admin_required
def users(): return render_template("users.html",users=User.query.order_by(User.id).all())
@app.post("/users")
@login_required
@admin_required
def user_create():
    name=request.form.get("username","").strip(); password=request.form.get("password",""); role=request.form.get("role")
    if not name or len(password)<8 or role not in ("admin","inspector"): flash("用户名必填，密码至少 8 位","error")
    elif User.query.filter_by(username=name).first(): flash("用户名已存在","error")
    else: db.session.add(User(username=name,password_hash=generate_password_hash(password),role=role,active=True)); db.session.commit(); flash("用户已创建","ok")
    return redirect(url_for("users"))
@app.post("/users/<int:uid>/toggle")
@login_required
@admin_required
def user_toggle(uid):
    u=db.session.get(User,uid)
    if not u: abort(404)
    if u.id==current_user().id: flash("不能禁用当前登录账号","error")
    else: u.active=not u.active; db.session.commit()
    return redirect(url_for("users"))

@app.errorhandler(403)
def e403(e): return render_template("error.html",code=403,message="无权访问"),403
@app.errorhandler(404)
def e404(e): return render_template("error.html",code=404,message="记录不存在或无权查看"),404
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT","8000")))
