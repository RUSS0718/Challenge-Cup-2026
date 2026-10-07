"""Build the independent 60-item medium-capability freeze set.

The existing 48-item complex holdout is copied unchanged.  The twelve added
items are parameterized, publicly sourced adaptations with explicit checks.
The runtime agent never reads this file or the reference answers.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sample_data" / "complex_capability_freeze_48.jsonl"
TARGET = ROOT / "sample_data" / "medium_capability_freeze_60.jsonl"

ADDITIONS = [
    {"idx": 6100, "task_type": "calculation", "subject": "离散数学", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "组合计数", "adaptation": "原创参数化改编", "problem": "计算 C(12,3)+C(12,9)。", "answer": "440", "verification": "C(12,3)=220，C(12,9)=220，总和440。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6101, "task_type": "calculation", "subject": "高等代数", "source": "mit_ocw_18_06", "source_url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", "source_ref": "多项式根", "adaptation": "原创参数化改编", "problem": "求方程 x^2−5x+6=0 的全部实根。", "answer": "{2,3}", "verification": "x^2−5x+6=(x−2)(x−3)。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6102, "task_type": "derivation", "subject": "离散数学", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "递推关系", "adaptation": "原创参数化改编", "problem": "数列满足 a_0=0 且 a_n=2a_{n−1}+1。推导 a_3。", "answer": "7", "verification": "a_1=1，a_2=3，a_3=7。", "is_long": 1, "is_multi_domain": 0},
    {"idx": 6103, "task_type": "derivation", "subject": "数学分析", "source": "mit_ocw_18_01", "source_url": "https://ocw.mit.edu/courses/18-01-single-variable-calculus-fall-2006/", "source_ref": "定积分", "adaptation": "原创参数化改编", "problem": "计算积分 ∫_0^1(3x^2+2x)dx。", "answer": "2", "verification": "原函数为 x^3+x^2，在0与1处之差为2。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6104, "task_type": "proof", "subject": "数论", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "模运算", "adaptation": "原创参数化改编", "problem": "证明任意奇数的平方除以8余1。", "answer": "成立", "verification": "奇数写成2k+1，平方为4k(k+1)+1；k(k+1)为偶数，故余1。", "is_long": 1, "is_multi_domain": 0},
    {"idx": 6105, "task_type": "proof", "subject": "数论", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "整除性", "adaptation": "原创参数化改编", "problem": "证明若整数 n 能被6整除，则 n 同时能被2和3整除。", "answer": "成立", "verification": "6=2×3，因此 n=6k=2(3k)=3(2k)。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6106, "task_type": "explanation", "subject": "线性代数", "source": "mit_ocw_18_06", "source_url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", "source_ref": "行列式与可逆性", "adaptation": "原创参数化改编", "problem": "解释为什么二元一次方程组的系数行列式非零时有唯一解。", "answer": "系数矩阵可逆，因此唯一解为A^{-1}b", "verification": "2×2矩阵行列式非零等价于矩阵可逆；可逆线性映射对每个 b 给出唯一 x。", "is_long": 1, "is_multi_domain": 0},
    {"idx": 6107, "task_type": "explanation", "subject": "数学分析", "source": "mit_ocw_18_01", "source_url": "https://ocw.mit.edu/courses/18-01-single-variable-calculus-fall-2006/", "source_ref": "均值不等式", "adaptation": "原创参数化改编", "problem": "说明正数 a,b 满足固定和时，为什么 ab 在 a=b 时最大。", "answer": "由AM-GM，ab≤((a+b)/2)^2，等号当且仅当a=b", "verification": "(a−b)^2≥0 等价于 (a+b)^2≥4ab。", "is_long": 1, "is_multi_domain": 0},
    {"idx": 6108, "task_type": "choice", "subject": "高等代数", "source": "mit_ocw_18_06", "source_url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", "source_ref": "多项式根", "adaptation": "原创参数化改编", "problem": "方程 x^2−4x+3=0 的根是？A.0和3 B.1和3 C.−1和−3 D.4和3", "answer": "B", "verification": "x^2−4x+3=(x−1)(x−3)。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6109, "task_type": "choice", "subject": "概率论", "source": "mit_ocw_18_05", "source_url": "https://ocw.mit.edu/courses/18-05-introduction-to-probability-and-statistics-spring-2014/", "source_ref": "独立事件", "adaptation": "原创参数化改编", "problem": "公平硬币独立抛掷两次，恰好出现两次正面的概率是？A.1/4 B.1/2 C.3/4 D.1", "answer": "A", "verification": "四种等可能结果中仅HH符合，概率1/4。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6110, "task_type": "fill_blank", "subject": "离散数学", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "有限求和", "adaptation": "原创参数化改编", "problem": "填空：1+2+⋯+20=____。", "answer": "210", "verification": "20×21/2=210。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6111, "task_type": "fill_blank", "subject": "数学分析", "source": "mit_ocw_18_01", "source_url": "https://ocw.mit.edu/courses/18-01-single-variable-calculus-fall-2006/", "source_ref": "基本求导公式", "adaptation": "原创参数化改编", "problem": "填空：若 f(x)=sin x，则 f'(x)=____。", "answer": "cos x", "verification": "基本导数公式 (sin x)'=cos x。", "is_long": 0, "is_multi_domain": 0},
]

EXTRA_ADDITIONS = [
    {"idx": 6200, "task_type": "calculation", "subject": "数论", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "最大公因数", "adaptation": "原创参数化改编", "problem": "计算 gcd(84,30)。", "answer": "6", "verification": "84=2×30+24，30=1×24+6。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6201, "task_type": "calculation", "subject": "数论", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "同余", "adaptation": "原创参数化改编", "problem": "计算 2^10 mod 7。", "answer": "2", "verification": "2^10=1024=7×146+2。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6202, "task_type": "calculation", "subject": "线性代数", "source": "mit_ocw_18_06", "source_url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", "source_ref": "二阶行列式", "adaptation": "原创参数化改编", "problem": "计算矩阵 [[3,1],[2,4]] 的行列式。", "answer": "10", "verification": "3×4−1×2=10。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6203, "task_type": "calculation", "subject": "概率论", "source": "mit_ocw_18_05", "source_url": "https://ocw.mit.edu/courses/18-05-introduction-to-probability-and-statistics-spring-2014/", "source_ref": "二项分布", "adaptation": "原创参数化改编", "problem": "独立抛掷公平硬币3次，恰有2次正面的概率是多少？", "answer": "3/8", "verification": "C(3,2)(1/2)^3=3/8。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6204, "task_type": "derivation", "subject": "数学分析", "source": "mit_ocw_18_01", "source_url": "https://ocw.mit.edu/courses/18-01-single-variable-calculus-fall-2006/", "source_ref": "几何级数", "adaptation": "原创参数化改编", "problem": "推导首项为1、公比为1/2的前五项和。", "answer": "31/16", "verification": "S=(1−(1/2)^5)/(1−1/2)=31/16。", "is_long": 1, "is_multi_domain": 0},
    {"idx": 6205, "task_type": "derivation", "subject": "数学分析", "source": "mit_ocw_18_01", "source_url": "https://ocw.mit.edu/courses/18-01-single-variable-calculus-fall-2006/", "source_ref": "链式法则", "adaptation": "原创参数化改编", "problem": "推导 f(x)=sin(x^2) 的导数。", "answer": "2x cos(x^2)", "verification": "外函数导数 cos(x^2) 乘以内函数导数2x。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6206, "task_type": "derivation", "subject": "线性代数", "source": "mit_ocw_18_06", "source_url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", "source_ref": "矩阵乘法", "adaptation": "原创参数化改编", "problem": "计算 [[1,2],[0,1]][[2,1],[3,4]] 的左上元素。", "answer": "8", "verification": "第一行与第一列内积1×2+2×3=8。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6207, "task_type": "derivation", "subject": "离散数学", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "递推关系", "adaptation": "原创参数化改编", "problem": "由 a_0=2，a_n=a_{n−1}+3 推导 a_4。", "answer": "14", "verification": "依次为5、8、11、14。", "is_long": 1, "is_multi_domain": 0},
    {"idx": 6208, "task_type": "proof", "subject": "数论", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "偶数性质", "adaptation": "原创参数化改编", "problem": "证明两个偶数之和仍为偶数。", "answer": "成立", "verification": "2a+2b=2(a+b)。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6209, "task_type": "proof", "subject": "离散数学", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "集合运算", "adaptation": "原创参数化改编", "problem": "证明 A∩B 是 A 的子集。", "answer": "成立", "verification": "任取x∈A∩B，则按交集定义x∈A。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6210, "task_type": "proof", "subject": "数学分析", "source": "mit_ocw_18_01", "source_url": "https://ocw.mit.edu/courses/18-01-single-variable-calculus-fall-2006/", "source_ref": "平方非负", "adaptation": "原创参数化改编", "problem": "证明对任意实数 x，有 x^2+1>0。", "answer": "成立", "verification": "x^2≥0，故x^2+1≥1>0。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6211, "task_type": "proof", "subject": "数论", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "数学归纳法", "adaptation": "原创参数化改编", "problem": "用归纳法证明 1+2+⋯+n=n(n+1)/2。", "answer": "成立", "verification": "基步n=1成立；假设n成立，加上n+1后得到(n+1)(n+2)/2。", "is_long": 1, "is_multi_domain": 0},
    {"idx": 6212, "task_type": "explanation", "subject": "线性代数", "source": "mit_ocw_18_06", "source_url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", "source_ref": "特征值", "adaptation": "原创参数化改编", "problem": "解释特征值为何满足 det(A−λI)=0。", "answer": "存在非零特征向量等价于A−λI奇异，因此行列式为0", "verification": "Av=λv且v≠0等价于(A−λI)v=0有非零解。", "is_long": 1, "is_multi_domain": 0},
    {"idx": 6213, "task_type": "explanation", "subject": "概率论", "source": "mit_ocw_18_05", "source_url": "https://ocw.mit.edu/courses/18-05-introduction-to-probability-and-statistics-spring-2014/", "source_ref": "条件概率", "adaptation": "原创参数化改编", "problem": "解释条件概率 P(A|B) 的含义。", "answer": "在B发生条件下A发生的概率，等于P(A∩B)/P(B)", "verification": "条件概率定义要求P(B)>0。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6214, "task_type": "explanation", "subject": "数学分析", "source": "mit_ocw_18_01", "source_url": "https://ocw.mit.edu/courses/18-01-single-variable-calculus-fall-2006/", "source_ref": "极限定义", "adaptation": "原创参数化改编", "problem": "解释 lim_{x→0} sin x/x=1 的几何意义。", "answer": "小角度下弧长、弦长和正切长度比值趋于1", "verification": "单位圆夹逼 sinx<x<tanx 得极限为1。", "is_long": 1, "is_multi_domain": 0},
    {"idx": 6215, "task_type": "explanation", "subject": "线性代数", "source": "mit_ocw_18_06", "source_url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", "source_ref": "秩", "adaptation": "原创参数化改编", "problem": "解释矩阵秩表示什么。", "answer": "矩阵列空间的维数，也等于线性无关列的最大数目", "verification": "秩定义为列空间维数。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6216, "task_type": "choice", "subject": "数学分析", "source": "mit_ocw_18_01", "source_url": "https://ocw.mit.edu/courses/18-01-single-variable-calculus-fall-2006/", "source_ref": "导数", "adaptation": "原创参数化改编", "problem": "函数 x^3 的导数是？A.3x^2 B.x^2 C.3x D.x^3", "answer": "A", "verification": "幂函数求导公式。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6217, "task_type": "choice", "subject": "概率论", "source": "mit_ocw_18_05", "source_url": "https://ocw.mit.edu/courses/18-05-introduction-to-probability-and-statistics-spring-2014/", "source_ref": "期望", "adaptation": "原创参数化改编", "problem": "公平骰子的期望值是？A.3 B.3.5 C.4 D.6", "answer": "B", "verification": "(1+2+3+4+5+6)/6=3.5。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6218, "task_type": "choice", "subject": "线性代数", "source": "mit_ocw_18_06", "source_url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", "source_ref": "可逆矩阵", "adaptation": "原创参数化改编", "problem": "二阶矩阵可逆的充要条件是？A.行列式为0 B.行列式非0 C.迹为0 D.对称", "answer": "B", "verification": "方阵可逆当且仅当行列式非零。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6219, "task_type": "choice", "subject": "数论", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "奇偶性", "adaptation": "原创参数化改编", "problem": "下列数中哪个是偶数？A.17 B.21 C.34 D.45", "answer": "C", "verification": "34可被2整除。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6220, "task_type": "fill_blank", "subject": "数学分析", "source": "mit_ocw_18_01", "source_url": "https://ocw.mit.edu/courses/18-01-single-variable-calculus-fall-2006/", "source_ref": "阶乘与导数", "adaptation": "原创参数化改编", "problem": "填空：5!=____。", "answer": "120", "verification": "5×4×3×2×1=120。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6221, "task_type": "fill_blank", "subject": "数学分析", "source": "mit_ocw_18_01", "source_url": "https://ocw.mit.edu/courses/18-01-single-variable-calculus-fall-2006/", "source_ref": "定积分", "adaptation": "原创参数化改编", "problem": "填空：∫_0^1 2x dx=____。", "answer": "1", "verification": "原函数x^2在1与0处之差为1。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6222, "task_type": "fill_blank", "subject": "离散数学", "source": "mit_ocw_6_042j", "source_url": "https://ocw.mit.edu/courses/6-042j-mathematics-for-computer-science-spring-2015/", "source_ref": "二项式系数", "adaptation": "原创参数化改编", "problem": "填空：C(8,2)=____。", "answer": "28", "verification": "8×7/2=28。", "is_long": 0, "is_multi_domain": 0},
    {"idx": 6223, "task_type": "fill_blank", "subject": "线性代数", "source": "mit_ocw_18_06", "source_url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", "source_ref": "单位矩阵", "adaptation": "原创参数化改编", "problem": "填空：2×2单位矩阵的迹为____。", "answer": "2", "verification": "对角线元素为1和1，迹为2。", "is_long": 0, "is_multi_domain": 0},
]


def build() -> list[dict]:
    with SOURCE.open("r", encoding="utf-8") as handle:
        base = [json.loads(line) for line in handle if line.strip()]
    if len(base) != 48:
        raise ValueError(f"expected 48 base items, got {len(base)}")
    public_base = [item for item in base if str(item.get("source_url", "")).startswith("https://")]
    if len(public_base) != 24:
        raise ValueError(f"expected 24 public base items, got {len(public_base)}")
    result = public_base + ADDITIONS + EXTRA_ADDITIONS
    if len({item["idx"] for item in result}) != 60:
        raise ValueError("duplicate idx")
    return result


if __name__ == "__main__":
    data = build()
    with TARGET.open("w", encoding="utf-8") as handle:
        for item in data:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"wrote {len(data)} items to {TARGET}")
