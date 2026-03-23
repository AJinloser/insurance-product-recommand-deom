"""
保险产品推荐引擎 —— 可视化测试套件

功能：
  - 独立运行每个测试用例或批量运行
  - 生成浏览器可视化报告（仿 ChatGPT 对话气泡）

用法：
  python test_runner.py --list                 # 列出所有用例
  python test_runner.py --case 3               # 仅运行第 3 号用例
  python test_runner.py --case 1,3,7           # 运行第 1、3、7 号
  python test_runner.py --all                  # 运行所有用例
  python test_runner.py --all --skip-load      # 跳过数据重载（复用已有 DB）
  python test_runner.py --report-only          # 不运行测试，仅从已有结果生成报告

报告输出：test_report.html （浏览器打开即可查看）
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from src import (
    InsuranceRecommendationAgent,
    RecommendationInput,
    Settings,
    UserProfile,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("test_runner")

RESULTS_FILE = Path("test_results.json")
REPORT_FILE = Path("test_report.html")

# ═══════════════════════════════════════════════════════════════
#  测试用例定义
# ═══════════════════════════════════════════════════════════════

TEST_CASES: list[dict] = [
    # ── 1: 零上下文 ─────────────────────────────────────────
    {
        "id": 1,
        "name": "零上下文 + 极度模糊需求",
        "description": "验证系统在信息极度不足时的鲁棒性，应选择默认类别并返回合理推荐",
        "expected_category": "百万医疗险",
        "tags": ["鲁棒性", "零上下文"],
        "input": RecommendationInput(
            dialogue_history=[],
            query="我想买份医疗保险",
            user_profile=UserProfile(),
        ),
    },
    # ── 2: 百万医疗 — 预算敏感 ─────────────────────────────
    {
        "id": 2,
        "name": "预算敏感 — 低预算百万医疗",
        "description": "明确预算上限触发硬过滤，应路由至百万医疗类并返回低价产品",
        "expected_category": "百万医疗险",
        "tags": ["百万医疗", "预算过滤", "硬过滤"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "我预算有限，想找最便宜的医疗险"},
                {"role": "assistant", "content": "好的，请问您的年龄和是否有社保？"},
                {"role": "user", "content": "30岁，有社保，年预算不超过400元"},
            ],
            query="帮我推荐年保费400元以内、保额最高的百万医疗险",
            user_profile=UserProfile(
                age=30,
                has_social_insurance=True,
                budget_max=400.0,
            ),
        ),
    },
    # ── 3: 百万医疗 — 老年人年龄边界 ──────────────────────
    {
        "id": 3,
        "name": "老年人投保 — 68岁边界",
        "description": "68岁应排除大量产品，测试最高投保年龄硬过滤和免赔额偏好",
        "expected_category": "百万医疗险",
        "tags": ["百万医疗", "年龄边界", "硬过滤", "老年人"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "我母亲68岁了，还能买医疗险吗？"},
                {"role": "assistant", "content": "68岁确实受到较多限制，请问她有医保吗？"},
                {"role": "user", "content": "有退休职工医保"},
                {"role": "assistant", "content": "好的，对免赔额有什么要求吗？"},
                {"role": "user", "content": "免赔额不要太高，毕竟老人看病频率高"},
            ],
            query="帮我68岁的母亲找一款还能投保的医疗险，最好免赔额低一些",
            user_profile=UserProfile(
                age=68,
                has_social_insurance=True,
                budget_max=5000.0,
                health_conditions=["高血压"],
            ),
        ),
    },
    # ── 4: 百万医疗 — 保证续保关注 ────────────────────────
    {
        "id": 4,
        "name": "续保稳定性优先 — 长期持有",
        "description": "关注保证续保期间和费率可调性，权重应偏向基本信息和保费维度",
        "expected_category": "百万医疗险",
        "tags": ["百万医疗", "续保", "长期价值"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "我最怕的是买了几年之后保险公司不让续保了"},
                {"role": "assistant", "content": "理解您的顾虑。保证续保是很重要的指标。请问您的年龄和预算？"},
                {"role": "user", "content": "28岁，有社保，预算500以内就行"},
            ],
            query="推荐保证续保期间最长、续保最稳定的百万医疗险",
            user_profile=UserProfile(
                age=28,
                has_social_insurance=True,
                budget_max=500.0,
            ),
        ),
    },
    # ── 5: 中端医疗 — 特需部 + 肿瘤 ──────────────────────
    {
        "id": 5,
        "name": "特需部 + 肿瘤专项 — 中端医疗",
        "description": "布尔字段过滤（特需部=是）+ 特殊保险责任权重提升",
        "expected_category": "中端医疗保险",
        "tags": ["中端医疗", "布尔过滤", "肿瘤", "特需部"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "家里有肿瘤家族史，想找覆盖特需部的医疗险"},
                {"role": "assistant", "content": "理解您的担忧。请问您的年龄、是否有社保？预算大概多少？"},
                {"role": "user", "content": "35岁，有社保，预算2000元左右"},
                {"role": "assistant", "content": "好的，您对质子重离子治疗、特药保障这些有要求吗？"},
                {"role": "user", "content": "当然需要，最好都能覆盖"},
            ],
            query="推荐覆盖特需部、质子重离子治疗和特药的中端医疗险，预算2000以内",
            user_profile=UserProfile(
                age=35,
                has_social_insurance=True,
                budget_max=2000.0,
                health_conditions=["肿瘤家族史"],
            ),
        ),
    },
    # ── 6: 中端医疗 — 多轮长对话 ─────────────────────────
    {
        "id": 6,
        "name": "多轮长对话 — 需求逐步细化",
        "description": "从长对话中提取多维度需求：特需部、外购药、心脑血管、预算区间",
        "expected_category": "中端医疗保险",
        "tags": ["中端医疗", "多轮对话", "需求提取"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "你好，我想了解一下医疗保险"},
                {"role": "assistant", "content": "好的，医疗保险主要分为百万医疗、中端医疗和高端医疗三个层次。百万医疗最实惠，高端医疗保障最全面。请问您有什么具体需求吗？"},
                {"role": "user", "content": "我不太懂保险，你能帮我分析一下吗？我30岁，有社保，在北京工作"},
                {"role": "assistant", "content": "好的。请问您主要关注哪些方面？比如是否需要覆盖特需部？对免赔额有要求吗？有没有特别关注的疾病类型？"},
                {"role": "user", "content": "我爸去年查出心脑血管疾病，所以我比较担心这方面。特需部能去当然好，但预算也不能太高"},
                {"role": "assistant", "content": "理解。那我帮您筛选覆盖心脑血管相关保障且含特需部的产品。您的预算大概在什么范围？"},
                {"role": "user", "content": "1500到2000之间吧"},
                {"role": "assistant", "content": "好的，最后确认一下：您是否需要外购药保障？就是说万一需要用医院外购买的药物，保险能报销"},
                {"role": "user", "content": "这个当然需要，听说很多靶向药都需要外购"},
                {"role": "assistant", "content": "了解，那我来帮您综合推荐"},
            ],
            query="综合以上对话，帮我推荐覆盖特需部、外购药，关注心脑血管保障的中端医疗险，预算1500-2000",
            user_profile=UserProfile(
                age=30,
                has_social_insurance=True,
                budget_min=1500.0,
                budget_max=2000.0,
                location="北京",
                health_conditions=["心脑血管家族史"],
            ),
        ),
    },
    # ── 7: 中端医疗 — 新生儿投保 ─────────────────────────
    {
        "id": 7,
        "name": "新生儿投保 — 0岁宝宝",
        "description": "特殊年龄段（0岁），测试年龄边界、婴幼儿保费和保障全面性偏好",
        "expected_category": "中端医疗保险",
        "tags": ["中端医疗", "年龄边界", "新生儿"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "宝宝刚出生2个月，想给他买份医疗险"},
                {"role": "assistant", "content": "恭喜！请问宝宝有上少儿医保吗？"},
                {"role": "user", "content": "有的，已经办好了"},
                {"role": "assistant", "content": "好的，百万医疗比较实惠，中端医疗门诊也能报。您倾向哪种？"},
                {"role": "user", "content": "孩子小经常看门诊，中端吧，能覆盖门诊最好"},
            ],
            query="给2个月大的宝宝推荐中端医疗险，最好能覆盖门诊，预算2000以内",
            user_profile=UserProfile(
                age=0,
                has_social_insurance=True,
                budget_max=2000.0,
                extra={"relationship": "子女", "baby_age_days": 60},
            ),
        ),
    },
    # ── 8: 高端医疗 — 全球就医 ───────────────────────────
    {
        "id": 8,
        "name": "高端全球医疗 — 高预算海外就医",
        "description": "高预算场景，应命中高端医疗类产品，关注私立医院和全球保障",
        "expected_category": "高端医疗保险",
        "tags": ["高端医疗", "高预算", "全球保障", "私立医院"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "我需要一款高端医疗险，经常出差海外"},
                {"role": "assistant", "content": "请问您需要覆盖美国地区吗？"},
                {"role": "user", "content": "不需要美国，全球除美即可"},
                {"role": "assistant", "content": "好的，您对私立医院和门诊保障有要求吗？"},
                {"role": "user", "content": "一定要涵盖私立医院，门诊保障也需要"},
                {"role": "assistant", "content": "了解。请问年龄和预算范围？"},
                {"role": "user", "content": "40岁，有社保，预算3万以内都可以接受"},
            ],
            query="推荐涵盖私立医院、有门诊保障的全球除美高端医疗险",
            user_profile=UserProfile(
                age=40,
                has_social_insurance=True,
                budget_max=30000.0,
                location="上海",
            ),
        ),
    },
    # ── 9: 高端医疗 — 心理 + 中医 ───────────────────────
    {
        "id": 9,
        "name": "心理健康 + 中医 — 小众需求",
        "description": "小众保障需求（心理治疗+中医），仅高端医疗可覆盖，测试类别路由",
        "expected_category": "高端医疗保险",
        "tags": ["高端医疗", "小众需求", "心理治疗", "中医"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "我最近工作压力很大，经常需要看心理医生"},
                {"role": "assistant", "content": "心理咨询费用确实不低。您希望保险能覆盖这部分吗？"},
                {"role": "user", "content": "是的，我同时也在做中医调理，希望也能报销"},
            ],
            query="推荐能同时覆盖心理治疗和中医治疗的医疗险",
            user_profile=UserProfile(
                age=32,
                has_social_insurance=True,
                location="北京",
                health_conditions=["焦虑症"],
            ),
        ),
    },
    # ── 10: 矛盾需求 — 低预算 + 高端特征 ────────────────
    {
        "id": 10,
        "name": "矛盾需求 — 低预算想要高端保障",
        "description": "预算仅1000但想要特需部+门诊，测试系统对矛盾信号的处理",
        "expected_category": "中端医疗保险",
        "tags": ["矛盾需求", "边界场景"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "我想要能去特需部、有门诊报销、还能全球就医的医疗险"},
                {"role": "assistant", "content": "这些需求通常需要中端或高端医疗险，预算大概多少？"},
                {"role": "user", "content": "我一年最多只能出1000块"},
            ],
            query="预算1000以内，推荐能去特需部且有门诊保障的医疗险",
            user_profile=UserProfile(
                age=28,
                has_social_insurance=True,
                budget_max=1000.0,
            ),
        ),
    },
    # ── 11: 无社保用户 ──────────────────────────────────
    {
        "id": 11,
        "name": "无社保用户 — 自由职业者",
        "description": "无社保影响保费和赔付比例，测试系统是否正确处理无社保场景",
        "expected_category": "百万医疗险",
        "tags": ["百万医疗", "无社保", "特殊人群"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "我是自由职业者，没有社保"},
                {"role": "assistant", "content": "没有社保的话保费会略高。请问您的年龄和预算？"},
                {"role": "user", "content": "25岁，预算800以内"},
            ],
            query="没有社保，推荐性价比最高的百万医疗险",
            user_profile=UserProfile(
                age=25,
                has_social_insurance=False,
                budget_max=800.0,
            ),
        ),
    },
    # ── 12: 显式类别指定 — 用户点名高端 ─────────────────
    {
        "id": 12,
        "name": "显式指定高端 — 直付网络关注",
        "description": "用户明确指定高端医疗，关注直付网络和昂贵医院覆盖",
        "expected_category": "高端医疗保险",
        "tags": ["高端医疗", "显式指定", "直付"],
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "我就要高端医疗险，不考虑其他的"},
                {"role": "assistant", "content": "好的。请问您对直付网络有要求吗？"},
                {"role": "user", "content": "一定要有直付，我不想垫付然后再报销"},
                {"role": "assistant", "content": "理解。昂贵医院（如和睦家）需要覆盖吗？"},
                {"role": "user", "content": "最好能覆盖"},
            ],
            query="推荐有直付网络、覆盖昂贵医院的高端医疗险",
            user_profile=UserProfile(
                age=38,
                has_social_insurance=True,
                budget_max=50000.0,
                location="上海",
            ),
        ),
    },
]


# ═══════════════════════════════════════════════════════════════
#  序列化 helpers
# ═══════════════════════════════════════════════════════════════

def _input_to_dict(inp: RecommendationInput) -> dict:
    return {
        "dialogue_history": inp.dialogue_history,
        "query": inp.query,
        "user_profile": inp.user_profile.model_dump(exclude_none=True),
    }


def _run_single(
    agent: InsuranceRecommendationAgent, tc: dict
) -> dict:
    """Run one test case and return a serializable result dict."""
    inp = tc["input"]
    t0 = time.time()
    output = agent.recommend(inp)
    elapsed = round(time.time() - t0, 1)

    recs = []
    if output.status == "success":
        for r in output.recommendations:
            recs.append({
                "product_id": r.product_id,
                "product_name": r.product_name,
                "recommendation_reason": r.recommendation_reason,
            })

    return {
        "id": tc["id"],
        "name": tc["name"],
        "description": tc["description"],
        "expected_category": tc["expected_category"],
        "tags": tc["tags"],
        "input": _input_to_dict(inp),
        "status": output.status,
        "error_message": output.error_message,
        "recommendations": recs,
        "elapsed_s": elapsed,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


# ═══════════════════════════════════════════════════════════════
#  运行器
# ═══════════════════════════════════════════════════════════════

def run_tests(
    case_ids: list[int] | None,
    skip_load: bool = False,
) -> list[dict]:
    settings = Settings.from_env()
    agent = InsuranceRecommendationAgent(settings)

    if not skip_load:
        print("⏳ Loading data (force_reload=True) …")
        agent.load_data(force_reload=True)
        print("✅ Data loaded.\n")
    else:
        print("⏩ Skipping data reload (--skip-load).\n")

    cases = TEST_CASES
    if case_ids:
        id_set = set(case_ids)
        cases = [tc for tc in TEST_CASES if tc["id"] in id_set]
        if not cases:
            print(f"❌ No test cases match IDs: {case_ids}")
            agent.close()
            return []

    # Load previous results to merge
    prev: dict[int, dict] = {}
    if RESULTS_FILE.exists():
        try:
            for r in json.loads(RESULTS_FILE.read_text("utf-8")):
                prev[r["id"]] = r
        except Exception:
            pass

    results: list[dict] = []
    for tc in cases:
        header = f"[{tc['id']:>2d}/{len(TEST_CASES)}] {tc['name']}"
        print(f"{'━' * 60}")
        print(f"  {header}")
        print(f"  Query: {tc['input'].query}")
        print(f"{'━' * 60}")

        result = _run_single(agent, tc)
        results.append(result)
        prev[result["id"]] = result

        # Print summary
        status_icon = "✅" if result["status"] == "success" else "❌"
        print(f"\n  {status_icon} {result['status']}  |  "
              f"{len(result['recommendations'])} recommendations  |  "
              f"{result['elapsed_s']}s\n")
        if result["status"] == "failed":
            print(f"  Error: {result['error_message']}\n")

    agent.close()

    # Save merged results
    all_results = sorted(prev.values(), key=lambda r: r["id"])
    RESULTS_FILE.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n💾 Results saved to {RESULTS_FILE}")

    return all_results


# ═══════════════════════════════════════════════════════════════
#  HTML 报告生成
# ═══════════════════════════════════════════════════════════════

def generate_report(results: list[dict]) -> None:
    html = _build_html(results)
    REPORT_FILE.write_text(html, encoding="utf-8")
    print(f"📊 Report generated: {REPORT_FILE}")


def _build_html(results: list[dict]) -> str:
    results_json = json.dumps(results, ensure_ascii=False)
    return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>保险推荐引擎 — 测试报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}

:root {{
  --bg-main: #f7f7f8;
  --bg-sidebar: #1e1e2e;
  --bg-sidebar-hover: #2a2a3e;
  --bg-sidebar-active: #353550;
  --bg-chat: #ffffff;
  --bg-user-bubble: #2563eb;
  --bg-assistant-bubble: #f0f0f5;
  --bg-system-bubble: #fef3c7;
  --text-primary: #1a1a2e;
  --text-secondary: #6b7280;
  --text-sidebar: #c8c8d8;
  --text-sidebar-active: #ffffff;
  --text-user: #ffffff;
  --text-assistant: #1a1a2e;
  --border: #e5e7eb;
  --accent: #2563eb;
  --success: #10b981;
  --error: #ef4444;
  --warning: #f59e0b;
  --radius: 16px;
  --radius-sm: 8px;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
}}

body {{
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
    "PingFang SC", "Noto Sans SC", sans-serif;
  background: var(--bg-main);
  color: var(--text-primary);
  height: 100vh;
  display: flex;
  overflow: hidden;
}}

/* ── sidebar ─────────────────────────────── */
.sidebar {{
  width: 320px;
  min-width: 320px;
  background: var(--bg-sidebar);
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(255,255,255,0.06);
}}

.sidebar-header {{
  padding: 20px 16px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}}

.sidebar-header h1 {{
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}}

.sidebar-header p {{
  color: var(--text-sidebar);
  font-size: 12px;
}}

.sidebar-stats {{
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}}

.stat-badge {{
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 20px;
  font-weight: 500;
}}

.stat-badge.total {{ background: rgba(255,255,255,0.1); color: #e0e0e0; }}
.stat-badge.pass  {{ background: rgba(16,185,129,0.15); color: #6ee7b7; }}
.stat-badge.fail  {{ background: rgba(239,68,68,0.15); color: #fca5a5; }}
.stat-badge.pend  {{ background: rgba(245,158,11,0.15); color: #fde68a; }}

.case-list {{
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}}

.case-list::-webkit-scrollbar {{ width: 4px; }}
.case-list::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.15); border-radius: 4px; }}

.case-item {{
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.15s;
  display: flex;
  align-items: flex-start;
  gap: 10px;
}}

.case-item:hover {{ background: var(--bg-sidebar-hover); }}
.case-item.active {{ background: var(--bg-sidebar-active); }}

.case-num {{
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: rgba(255,255,255,0.1);
}}

.case-item.status-success .case-num {{ background: var(--success); }}
.case-item.status-failed  .case-num {{ background: var(--error); }}
.case-item.status-pending  .case-num {{ background: var(--warning); }}

.case-info {{ flex: 1; min-width: 0; }}

.case-info .name {{
  font-size: 13px;
  color: var(--text-sidebar);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}

.case-item.active .case-info .name {{ color: var(--text-sidebar-active); }}

.case-info .meta {{
  font-size: 11px;
  color: rgba(200,200,216,0.5);
  margin-top: 2px;
  display: flex;
  gap: 8px;
}}

/* ── main chat area ──────────────────────── */
.main {{
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}}

.chat-header {{
  padding: 16px 24px;
  background: var(--bg-chat);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}}

.chat-header .title {{
  font-size: 15px;
  font-weight: 600;
}}

.chat-header .badges {{
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}}

.tag {{
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  background: rgba(37,99,235,0.08);
  color: var(--accent);
  font-weight: 500;
}}

.tag.category {{
  background: rgba(16,185,129,0.1);
  color: #059669;
}}

.chat-body {{
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}}

.chat-body::-webkit-scrollbar {{ width: 6px; }}
.chat-body::-webkit-scrollbar-thumb {{ background: #d1d5db; border-radius: 6px; }}

/* ── bubbles ─────────────────────────────── */
.msg {{
  display: flex;
  gap: 10px;
  max-width: 85%;
  animation: fadeIn 0.25s ease;
}}

@keyframes fadeIn {{
  from {{ opacity: 0; transform: translateY(8px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}

.msg.user {{ align-self: flex-end; flex-direction: row-reverse; }}
.msg.assistant {{ align-self: flex-start; }}
.msg.system {{ align-self: center; max-width: 92%; }}

.avatar {{
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
}}

.msg.user .avatar {{ background: var(--bg-user-bubble); }}
.msg.assistant .avatar {{ background: #6366f1; }}

.bubble {{
  padding: 12px 16px;
  border-radius: var(--radius);
  line-height: 1.6;
  font-size: 14px;
  box-shadow: var(--shadow);
  word-break: break-word;
}}

.msg.user .bubble {{
  background: var(--bg-user-bubble);
  color: var(--text-user);
  border-bottom-right-radius: 4px;
}}

.msg.assistant .bubble {{
  background: var(--bg-assistant-bubble);
  color: var(--text-assistant);
  border-bottom-left-radius: 4px;
}}

.msg.system .bubble {{
  background: var(--bg-system-bubble);
  color: #92400e;
  border-radius: var(--radius-sm);
  font-size: 13px;
  text-align: center;
  width: 100%;
}}

.msg.final-query .bubble {{
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  box-shadow: 0 2px 8px rgba(37,99,235,0.3);
}}

/* ── profile card ────────────────────────── */
.profile-card {{
  background: linear-gradient(135deg, #f8fafc, #f0f4ff);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
  font-size: 13px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 6px 16px;
}}

.profile-card .field {{
  display: flex;
  gap: 6px;
}}

.profile-card .label {{
  color: var(--text-secondary);
  flex-shrink: 0;
}}

.profile-card .value {{
  font-weight: 500;
}}

/* ── recommendation card ─────────────────── */
.rec-card {{
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 16px;
  margin-top: 8px;
  transition: box-shadow 0.2s;
}}

.rec-card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}

.rec-card-header {{
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}}

.rec-rank {{
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}}

.rec-rank.r1 {{ background: linear-gradient(135deg, #f59e0b, #d97706); }}
.rec-rank.r2 {{ background: linear-gradient(135deg, #9ca3af, #6b7280); }}
.rec-rank.r3 {{ background: linear-gradient(135deg, #b45309, #92400e); }}

.rec-card-header .product-name {{
  font-size: 15px;
  font-weight: 600;
}}

.rec-card-header .product-id {{
  font-size: 11px;
  color: var(--text-secondary);
  background: #f3f4f6;
  padding: 1px 6px;
  border-radius: 4px;
}}

.rec-reason {{
  font-size: 13.5px;
  line-height: 1.75;
  color: #374151;
  white-space: pre-line;
}}

.rec-reason strong, .rec-reason b {{
  color: var(--text-primary);
}}

/* ── footer / status bar ─────────────────── */
.chat-footer {{
  padding: 12px 24px;
  background: var(--bg-chat);
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
}}

.status-dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 6px;
}}

.status-dot.ok   {{ background: var(--success); }}
.status-dot.err  {{ background: var(--error); }}
.status-dot.wait {{ background: var(--warning); }}

/* ── empty state ─────────────────────────── */
.empty-state {{
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  gap: 12px;
}}

.empty-state .icon {{ font-size: 48px; opacity: 0.3; }}
.empty-state p {{ font-size: 14px; }}

/* ── responsive ──────────────────────────── */
@media (max-width: 768px) {{
  .sidebar {{ width: 260px; min-width: 260px; }}
  .msg {{ max-width: 95%; }}
}}
</style>
</head>
<body>

<div class="sidebar">
  <div class="sidebar-header">
    <h1>保险推荐引擎测试</h1>
    <p>点击左侧用例查看对话详情</p>
  </div>
  <div class="sidebar-stats" id="stats"></div>
  <div class="case-list" id="caseList"></div>
</div>

<div class="main">
  <div class="chat-header" id="chatHeader">
    <span class="title">选择一个测试用例开始查看</span>
    <div class="badges"></div>
  </div>
  <div class="chat-body" id="chatBody">
    <div class="empty-state">
      <div class="icon">💬</div>
      <p>从左侧选择一个测试用例查看推荐对话</p>
    </div>
  </div>
  <div class="chat-footer" id="chatFooter">
    <span></span>
    <span>仅展示模式 — 不可发送消息</span>
  </div>
</div>

<script>
const DATA = {results_json};

// ── sidebar ──────────────────────────────────────
function renderSidebar() {{
  const list = document.getElementById('caseList');
  const stats = document.getElementById('stats');

  const total = DATA.length;
  const pass  = DATA.filter(d => d.status === 'success').length;
  const fail  = DATA.filter(d => d.status === 'failed').length;
  const pend  = total - pass - fail;

  stats.innerHTML = `
    <span class="stat-badge total">${{total}} 用例</span>
    <span class="stat-badge pass">${{pass}} 通过</span>
    ${{fail ? `<span class="stat-badge fail">${{fail}} 失败</span>` : ''}}
    ${{pend ? `<span class="stat-badge pend">${{pend}} 未运行</span>` : ''}}
  `;

  list.innerHTML = DATA.map(d => `
    <div class="case-item status-${{d.status || 'pending'}}" data-id="${{d.id}}" onclick="selectCase(${{d.id}})">
      <div class="case-num">${{d.id}}</div>
      <div class="case-info">
        <div class="name">${{d.name}}</div>
        <div class="meta">
          <span>${{d.expected_category}}</span>
          ${{d.elapsed_s ? `<span>${{d.elapsed_s}}s</span>` : ''}}
        </div>
      </div>
    </div>
  `).join('');
}}

// ── render a single case ─────────────────────────
function selectCase(id) {{
  document.querySelectorAll('.case-item').forEach(el => {{
    el.classList.toggle('active', +el.dataset.id === id);
  }});

  const d = DATA.find(d => d.id === id);
  if (!d) return;

  // header
  const header = document.getElementById('chatHeader');
  const statusCls = d.status === 'success' ? 'ok' : d.status === 'failed' ? 'err' : 'wait';
  header.innerHTML = `
    <span class="title">${{d.name}}</span>
    <div class="badges">
      <span class="tag category">${{d.expected_category}}</span>
      ${{d.tags.map(t => `<span class="tag">${{t}}</span>`).join('')}}
    </div>
  `;

  // body
  const body = document.getElementById('chatBody');
  let html = '';

  // system: description
  html += msgHTML('system', `📋 ${{d.description}}`);

  // profile card
  const prof = d.input.user_profile;
  if (prof && Object.keys(prof).length > 0) {{
    html += profileCardHTML(prof);
  }}

  // dialogue history
  const hist = d.input.dialogue_history || [];
  for (const m of hist) {{
    html += msgHTML(m.role === 'user' ? 'user' : 'assistant', m.content);
  }}

  // final query (highlighted)
  html += msgHTML('final-query user', d.input.query);

  // results
  if (d.status === 'failed') {{
    html += msgHTML('system', `❌ 推荐失败: ${{d.error_message || '未知错误'}}`);
  }} else if (d.recommendations && d.recommendations.length > 0) {{
    html += assistantRecsHTML(d.recommendations);
  }} else {{
    html += msgHTML('system', '⏳ 该用例尚未运行');
  }}

  body.innerHTML = html;
  body.scrollTop = body.scrollHeight;

  // footer
  const footer = document.getElementById('chatFooter');
  const dotCls = d.status === 'success' ? 'ok' : d.status === 'failed' ? 'err' : 'wait';
  const statusText = d.status === 'success'
    ? `${{d.recommendations.length}} 个推荐  ·  耗时 ${{d.elapsed_s}}s`
    : d.status === 'failed'
      ? '推荐失败'
      : '未运行';
  footer.innerHTML = `
    <span><span class="status-dot ${{dotCls}}"></span>${{statusText}}${{d.timestamp ? '  ·  ' + d.timestamp : ''}}</span>
    <span>仅展示模式 — 不可发送消息</span>
  `;
}}

function msgHTML(cls, text) {{
  const isUser = cls.includes('user');
  const isSystem = cls.includes('system');
  const avatarLetter = isUser ? 'U' : 'A';

  if (isSystem) {{
    return `<div class="msg system"><div class="bubble">${{esc(text)}}</div></div>`;
  }}

  return `
    <div class="msg ${{cls}}">
      <div class="avatar">${{avatarLetter}}</div>
      <div class="bubble">${{esc(text)}}</div>
    </div>`;
}}

function profileCardHTML(prof) {{
  const labels = {{
    age: '年龄', has_social_insurance: '社保', budget_min: '预算下限',
    budget_max: '预算上限', location: '所在地', health_conditions: '健康状况',
    family_members: '家庭人数', extra: '附加信息',
  }};
  let fields = '';
  for (const [k, v] of Object.entries(prof)) {{
    if (v == null) continue;
    let display = v;
    if (k === 'has_social_insurance') display = v ? '有' : '无';
    else if (k === 'budget_min' || k === 'budget_max') display = '¥' + v;
    else if (Array.isArray(v)) display = v.join('、');
    else if (typeof v === 'object') display = JSON.stringify(v);
    fields += `<div class="field"><span class="label">${{labels[k] || k}}:</span><span class="value">${{esc(String(display))}}</span></div>`;
  }}
  return `
    <div class="msg system" style="max-width:92%">
      <div style="width:100%">
        <div style="font-size:12px;color:#6b7280;margin-bottom:6px;">👤 用户画像</div>
        <div class="profile-card">${{fields}}</div>
      </div>
    </div>`;
}}

function assistantRecsHTML(recs) {{
  let cards = '';
  recs.forEach((r, i) => {{
    const rankCls = i < 3 ? 'r' + (i + 1) : '';
    const reason = formatReason(r.recommendation_reason || '');
    cards += `
      <div class="rec-card">
        <div class="rec-card-header">
          <div class="rec-rank ${{rankCls}}">${{i + 1}}</div>
          <span class="product-name">${{esc(r.product_name)}}</span>
          <span class="product-id">ID: ${{r.product_id}}</span>
        </div>
        <div class="rec-reason">${{reason}}</div>
      </div>`;
  }});

  return `
    <div class="msg assistant">
      <div class="avatar">A</div>
      <div style="display:flex;flex-direction:column;gap:8px;min-width:0;flex:1">
        <div class="bubble" style="margin-bottom:0;">根据您的需求，为您推荐以下产品：</div>
        ${{cards}}
      </div>
    </div>`;
}}

function formatReason(text) {{
  return esc(text)
    .replace(/【(.*?)】/g, '<strong>【$1】</strong>')
    .replace(/\\n/g, '<br>');
}}

function esc(s) {{
  const el = document.createElement('span');
  el.textContent = s;
  return el.innerHTML;
}}

// ── init ─────────────────────────────────────────
renderSidebar();
if (DATA.length > 0) selectCase(DATA[0].id);
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="保险推荐引擎 — 可视化测试套件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python test_runner.py --list                列出所有用例
  python test_runner.py --case 3              仅运行第 3 号用例
  python test_runner.py --case 1,5,9          运行第 1、5、9 号
  python test_runner.py --all                 运行全部用例
  python test_runner.py --all --skip-load     复用已有 DB
  python test_runner.py --report-only         仅从已有结果生成报告
  python test_runner.py --all --open          运行后自动在浏览器打开报告
        """,
    )
    parser.add_argument("--list", action="store_true",
                        help="列出所有测试用例")
    parser.add_argument("--case", type=str, default=None,
                        help="运行指定用例（逗号分隔，如 1,3,7）")
    parser.add_argument("--all", action="store_true",
                        help="运行全部用例")
    parser.add_argument("--skip-load", action="store_true",
                        help="跳过数据重载，复用已有 insurance.db")
    parser.add_argument("--report-only", action="store_true",
                        help="不运行测试，仅从已有 test_results.json 生成 HTML 报告")
    parser.add_argument("--open", action="store_true",
                        help="生成报告后自动在浏览器中打开")

    args = parser.parse_args()

    if args.list:
        print(f"\n{'ID':>3s}  {'用例名称':<36s}  {'期望类别':<14s}  标签")
        print(f"{'─' * 80}")
        for tc in TEST_CASES:
            tags = ", ".join(tc["tags"])
            print(f"{tc['id']:>3d}  {tc['name']:<36s}  "
                  f"{tc['expected_category']:<14s}  {tags}")
        print(f"\n共 {len(TEST_CASES)} 个用例\n")
        return

    if args.report_only:
        if not RESULTS_FILE.exists():
            print(f"❌ {RESULTS_FILE} not found. Run tests first.")
            sys.exit(1)
        results = json.loads(RESULTS_FILE.read_text("utf-8"))
        generate_report(results)
        if args.open:
            webbrowser.open(str(REPORT_FILE.resolve()))
        return

    case_ids = None
    if args.case:
        try:
            case_ids = [int(x.strip()) for x in args.case.split(",")]
        except ValueError:
            print("❌ --case 参数格式错误，应为逗号分隔的数字，如 1,3,7")
            sys.exit(1)
    elif not args.all:
        parser.print_help()
        return

    results = run_tests(case_ids, skip_load=args.skip_load)
    if results:
        generate_report(results)
        if args.open:
            webbrowser.open(str(REPORT_FILE.resolve()))


if __name__ == "__main__":
    main()
