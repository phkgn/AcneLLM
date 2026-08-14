"""Routing va extraction adapter cho chat intake.

Doi ten tu ``chat/fallback`` o Phase 7. Ten cu sai: no noi "chi chay khi vo",
nhung ``intent_router.compute_route_flags`` chay tren 100% request. Ba tang
router thuc te, theo thu tu intake.py thu:

    llm_router (UnifiedIntake)  ->  semantic_router  ->  route_intent (rule)

Chi tang thu ba moi la fallback. Xem docstring intent_router.py.
"""
