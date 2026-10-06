"""MIL-STD-105E / ISO 2859-1 单次抽样、正常检验查询。"""
AQL_VALUES = ["0.010", "0.015", "0.025", "0.040", "0.065", "0.10", "0.15", "0.25", "0.40", "0.65", "1.0", "1.5", "2.5", "4.0", "6.5", "10.0"]
LEVELS = ["S-1", "S-2", "S-3", "S-4", "I", "II", "III"]
# Table I: lot upper bound followed by S-1, S-2, S-3, S-4, I, II, III.
LOT_CODE_ROWS = [
 (8,      ["A","A","A","A","A","A","B"]),
 (15,     ["A","A","A","A","A","B","C"]),
 (25,     ["A","A","B","B","B","C","D"]),
 (50,     ["A","B","B","C","C","D","E"]),
 (90,     ["B","B","C","C","C","E","F"]),
 (150,    ["B","B","C","D","D","F","G"]),
 (280,    ["B","C","D","E","E","G","H"]),
 (500,    ["B","C","D","E","F","H","J"]),
 (1200,   ["C","C","E","F","G","J","K"]),
 (3200,   ["C","D","E","G","H","K","L"]),
 (10000,  ["C","D","F","G","J","L","M"]),
 (35000,  ["C","D","F","H","K","M","N"]),
 (150000, ["D","E","G","J","L","N","P"]),
 (500000, ["D","E","G","J","M","P","Q"]),
 (10**30, ["D","E","H","K","N","Q","R"]),
]
CODES = ["A","B","C","D","E","F","G","H","J","K","L","M","N","P","Q","R"]
SIZES = [2,3,5,8,13,20,32,50,80,125,200,315,500,800,1250,2000]
CODE_SIZES = dict(zip(CODES, SIZES))
# Table II-A central plans lie on diagonals; arrows select the first plan below/above.
# Sum of zero-based code/AQL indices -> Ac for direct cells.
DIAGONAL_AC = {16:0, 17:1, 18:2, 19:3, 20:5, 21:7, 22:10, 23:14, 24:21}

def code_for(lot_size, level):
    if lot_size < 2: raise ValueError("批量数必须至少为 2")
    if level not in LEVELS: raise ValueError("无效检验水平")
    li = LEVELS.index(level)
    return next(row[li] for upper,row in LOT_CODE_ROWS if lot_size <= upper)

def plan_for(code, aql, lot_size=None):
    if code not in CODES: raise ValueError("无效样本量字码")
    aql = str(aql)
    if aql not in AQL_VALUES: raise ValueError("AQL 必须使用标准档位")
    ri, ci = CODES.index(code), AQL_VALUES.index(aql)
    total = ri + ci
    resolved = ri
    arrow = ""
    if total < 16:
        resolved += 16-total
        arrow = "down"
    elif total > 24:
        resolved -= total-24
        arrow = "up"
    if resolved < 0: resolved = 0
    if resolved >= len(CODES):
        # Table arrow reaches the 3150/0 plan below R. This is operationally
        # 100% inspection whenever the lot is no larger than 3150.
        size, resolved_code = 3150, "S*"
    else:
        size, resolved_code = SIZES[resolved], CODES[resolved]
    ac = DIAGONAL_AC[max(16, min(24, resolved + ci))]
    if lot_size is not None and size >= lot_size:
        return {"code": "100%", "size": int(lot_size), "ac": 0, "re": 1, "arrow": "full"}
    return {"code": resolved_code, "size": size, "ac": ac, "re": ac+1, "arrow": arrow}

def calculate(lot_size, level, aql_cri, aql_maj, aql_min):
    lot_size=int(lot_size)
    base=code_for(lot_size, level)
    raw={
      "cri": plan_for(base,aql_cri,lot_size),
      "maj": plan_for(base,aql_maj,lot_size),
      "min": plan_for(base,aql_min,lot_size),
    }
    operational=max(x["size"] for x in raw.values())
    if operational >= lot_size:
        op_code="100%"
        operational=lot_size
    else:
        op_code=max(raw.values(), key=lambda x:x["size"])["code"]
    return {"base_code":base,"code_letter":op_code,"sample_size":operational,"criteria":raw}
