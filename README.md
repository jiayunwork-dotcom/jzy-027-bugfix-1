# 柔索悬链标定服务

量弧垂推水平张力、再顺着这条张力铺出整档悬链曲线的 HTTP 服务。
只做柔索悬链几何这一块：**正算（H → 曲线）与反演（弧垂 → H）共用
同一套双曲关系**，标定结果里附带正算→反演的闭合误差作为验收证据。

Python 3.12 + Flask，单容器；具名几何档以本地 JSON 文件保存，
标定当次完成、不另建流水库。

## 数学约定

左支座 A 在 `(0,0)`，右支座 B 在 `(L,h)`：

| 符号 | 含义 |
|---|---|
| `L` | 档距（水平跨度），> 0 |
| `h` | 两端高差 y_B − y_A，可正可负（正：右端高） |
| `w` | 单位长度重量，> 0 |
| `H` | 水平张力，> 0 |
| `c` | 形状参数，`c = H / w` |

令 `a = L/(2c)`，倒悬链（向下垂）取对中形式：

```
p = asinh( h / (2 c sinh a) )
y(x) = c [ cosh((x − L/2)/c + p) − cosh(p − a) ]      # y(0)=0, y(L)=h
最低点  x_v = L/2 − c p
弧垂    f(x) = h x/L − y(x)
索长    S = c [ sinh(p+a) − sinh(p−a) ] = 2 c cosh p sinh a
```

- **等高** `h=0`：`p=0`，最低点在跨中，跨中弧垂 `c(cosh a − 1)`。
- **不等高**：最低点偏向低端；代码不用等高闭式硬套，统一走上面的
  双曲关系 + 对数二分反演。
- **可达性**：要求最低点位于两支座之间。最低点恰在较低支座处为边界，
  解 `(cosh v−1)/v = |h|/L` 得 `c_max = L/v`，故可行张力须满足
  `c = H/w ≤ c_max`。测点处对应一个**最小可实现弧垂** `f_min`，
  实测更小则判 `span_unreachable`（够不着），而不是编一个 H 画一条
  对不上测量的曲线。
- **矛盾**：测点落在支座处时弧垂恒为 0，却给出正实测弧垂，判
  `sag_contradiction`（弧垂与测点/高差互相矛盾）。
- **不使用抛物近似**：`wL²/(8H)` 在大垂度下系统偏短；大垂度验收档
  （`L=100, c=20`）下抛物值比悬链小 39%，测试将其卡死。

## 目录与分层

```
app/catenary.py    双曲正算：索形/弦线/弧垂/最低点/索长/可达边界
app/inversion.py   由弧垂反演 c、H（对数二分）+ 够不着分类
app/validation.py  入参检查（H、w、档距为正；弧垂为正；测点/取样档内）
app/storage.py     具名几何档的本地 JSON 原子读写
app/service.py     标定/正算编排与闭合误差
app/routes.py      HTTP 路由
app/errors.py      统一错误码与 HTTP 映射
wsgi.py            服务入口（0.0.0.0:8080）
tests/             锁住验收清单的自动化测试
```

## 构建与运行

```bash
docker build -t catenary-service .
docker run -p 8080:8080 -v $PWD/data:/data catenary-service
```

本地（无容器时）：

```bash
pip install -r requirements.txt
python wsgi.py          # http://localhost:8080
python -m pytest        # 跑测试（pytest 需另装）
```

数据文件路径可用环境变量 `CATENARY_STORE` 覆盖（容器默认 `/data/spans.json`）。

## API

### 具名几何档

`POST /api/spans` —— 登记 `{name, span, height_difference(默认0), w}`
`GET  /api/spans` —— 列出全部档（几何全文）
`GET  /api/spans/<name>`

### 标定（弧垂 → H → 整档曲线）

`POST /api/calibrate` —— 自带几何：
```json
{"span": 240, "height_difference": 18, "w": 10.5,
 "sag": 6.3234, "x": 120, "points": [0, 60, 120, 180, 240]}
```
`x` 缺省为跨中，`points` 缺省为档内均匀 21 点。

`POST /api/spans/<name>/calibrate` —— 点名档时几何已登记，只需：
```json
{"sag": 6.3234}            // x 默认跨中，也可显式给
```

返回含：`H, c, vertex_x, vertex_y, vertex_inside, length,
computed_sag, measurement, c_max_reachable, minimum_measurable_sag,
closure{..., rel_error, passed}, points[]`。

### 正算（H → 整档曲线）

`POST /api/forward`：
```json
{"H": 12000, "w": 10.5, "span": 240, "height_difference": 18,
 "points": [0, 120, 240]}
```
`POST /api/spans/<name>/forward`：点名档只需 `{H, points?}`。

### 错误

| HTTP | error | 触发 |
|---|---|---|
| 400 | `invalid_parameter` | H/w/档距非正、弧垂非正、测点或取样越界、缺字段、非 JSON |
| 404 | `span_not_found` | 档名对不上 |
| 409 | `span_exists` | 档名重复（可加 `"overwrite": true`） |
| 422 | `span_unreachable` | 弧垂小到最低点出档，够不着两个支座 |
| 422 | `sag_contradiction` | 弧垂与测点/高差矛盾（如支座处给正弧垂） |

## 验收测试对照

`tests/test_catenary.py` / `tests/test_http.py` 锁定：

1. 等高跨中弧垂对上闭式 `c(cosh(L/2c)−1)`；
2. 已知 H 正算弧垂 → 反演 H，相对误差 `< 1e-10`（对外容差 `1e-6`）；
3. 高差加大，最低点随高差单调偏向低端，且高低端镜像对称；
4. 大垂度档抛物近似偏短 30% 以上（悬链 102.65 vs 抛物 62.5）；
5. H 非正被拒；
6. 档距（及 w）非正被拒；
7. 弧垂与高差矛盾（支座处正弧垂）标定失败而非硬画；
另含：够不着失败、取样越界、非有限值、具名档持久化、HTTP 错误码映射。
