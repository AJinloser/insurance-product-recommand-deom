"""
保险产品推荐引擎 —— 多场景测试用例

覆盖维度：
  - 对话历史长短（无历史 / 短 / 长 / 多轮渐进）
  - 需求清晰度（模糊 / 明确 / 极精确）
  - 侧重方向（价格敏感 / 特殊保障 / 高端需求 / 特殊人群 / 心理健康）
  - 用户画像完整度（空画像 / 部分 / 完整）

运行前请确保:
  1. pip install -r requirements.txt
  2. 配置 .env 文件（参考 .env.example）
  3. data/ 目录下有 xlsx 保险产品文件
"""

import json
import logging
import time

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


# ═══════════════════════════════════════════════════════════════
#  测试用例定义
# ═══════════════════════════════════════════════════════════════

TEST_CASES: list[dict] = [
    # ── Case 1: 零上下文 + 模糊需求 ──────────────────────────
    # 目的：验证系统在信息极度不足时的鲁棒性，应返回跨类别的多元推荐
    {
        "name": "Case 1: 零上下文 + 极度模糊需求",
        "input": RecommendationInput(
            dialogue_history=[],
            query="我想买份医疗保险",
            user_profile=UserProfile(),
        ),
    },

    # ── Case 2: 预算敏感型 — 百万医疗 ────────────────────────
    # 目的：明确预算上限触发硬过滤，应仅返回百万医疗类低价产品
    {
        "name": "Case 2: 预算敏感 — 低预算百万医疗",
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

    # ── Case 3: 特需部 + 肿瘤保障 — 中端医疗 ────────────────
    # 目的：布尔字段过滤（特需部=是）+ 软性偏好（肿瘤/质子重离子）
    {
        "name": "Case 3: 特需部 + 肿瘤专项 — 中端医疗",
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

    # ── Case 4: 高端医疗 — 全球就医高预算 ────────────────────
    # 目的：高预算场景，应命中高端医疗类产品，关注私立医院和全球保障
    {
        "name": "Case 4: 高端全球医疗 — 高预算",
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

    # ── Case 5: 为新生儿投保 ─────────────────────────────────
    # 目的：特殊年龄段（0岁），测试年龄边界和婴幼儿保费字段
    {
        "name": "Case 5: 新生儿投保 — 0岁宝宝",
        "input": RecommendationInput(
            dialogue_history=[
                {"role": "user", "content": "宝宝刚出生2个月，想给他买份医疗险"},
                {"role": "assistant", "content": "恭喜！请问宝宝有上少儿医保吗？"},
                {"role": "user", "content": "有的，已经办好了"},
            ],
            query="给2个月大的宝宝推荐医疗险，保障全面一点，预算2000以内",
            user_profile=UserProfile(
                age=0,
                has_social_insurance=True,
                budget_max=2000.0,
                extra={"relationship": "子女", "baby_age_days": 60},
            ),
        ),
    },

    # ── Case 6: 老年人投保 — 年龄边界 ───────────────────────
    # 目的：测试最高投保年龄硬过滤，68岁应排除大量产品
    {
        "name": "Case 6: 老年人投保 — 68岁边界测试",
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

    # ── Case 7: 心理健康关注 + 中医需求 ─────────────────────
    # 目的：测试小众保障需求的检索能力（心理治疗 + 中医 = 高端医疗独有）
    {
        "name": "Case 7: 心理健康 + 中医 — 小众需求",
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

    # ── Case 8: 多轮长对话逐步细化 — 综合需求 ────────────────
    # 目的：测试从长对话中提取多维度需求的能力
    {
        "name": "Case 8: 多轮长对话 — 需求逐步细化",
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
]


# ═══════════════════════════════════════════════════════════════
#  执行器
# ═══════════════════════════════════════════════════════════════

def run_all_tests(agent: InsuranceRecommendationAgent) -> None:
    results: list[dict] = []

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"\n{'━' * 70}")
        print(f"  {tc['name']}")
        print(f"  Query: {tc['input'].query}")
        print(f"{'━' * 70}")

        t0 = time.time()
        output = agent.recommend(tc["input"])
        elapsed = time.time() - t0

        print(f"\n  Status : {output.status}  |  耗时: {elapsed:.1f}s")

        if output.status == "failed":
            print(f"  Error  : {output.error_message}")
        else:
            for j, rec in enumerate(output.recommendations, 1):
                print(f"\n  ── 推荐 #{j} ──")
                print(f"  产品ID   : {rec.product_id}")
                print(f"  产品名称 : {rec.product_name}")
                print(f"  推荐理由 :")
                for line in rec.recommendation_reason.split("\\n"):
                    print(f"    {line}")

        results.append({
            "case": tc["name"],
            "status": output.status,
            "count": len(output.recommendations),
            "elapsed_s": round(elapsed, 1),
        })

    # 汇总表
    print(f"\n\n{'═' * 70}")
    print("  测试汇总")
    print(f"{'═' * 70}")
    print(f"  {'测试用例':<40s} {'状态':<10s} {'推荐数':>5s} {'耗时':>6s}")
    print(f"  {'─' * 65}")
    for r in results:
        print(
            f"  {r['case']:<40s} {r['status']:<10s} "
            f"{r['count']:>5d} {r['elapsed_s']:>5.1f}s"
        )


def main() -> None:
    settings = Settings.from_env()
    agent = InsuranceRecommendationAgent(settings)

    agent.load_data(force_reload=True)

    run_all_tests(agent)

    agent.close()


if __name__ == "__main__":
    main()
