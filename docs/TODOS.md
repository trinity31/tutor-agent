# TODOS

## P2: 버튼 기반 간편 이해도 확인 옵션

**What:** 이해도 확인에서 개방형 텍스트 응답 외에 '자신 있음 / 애매함 / 모르겠음' 3버튼 간편 응답 옵션 추가
**Why:** 직장인이 출퇴근 중 모바일에서 긴 텍스트 입력은 high-friction. 버튼 탭만으로 이해도를 빠르게 기록할 수 있으면 사용성 향상
**Pros:** 모바일 사용성 대폭 개선, 응답률 증가 예상
**Cons:** 개방형 응답 대비 이해도 평가 정밀도 감소
**Context:** Codex 플랜 리뷰에서 지적. 이해도 확인 기본 구현(개방형) 완료 후 A/B 테스트로 검증 권장
**Effort:** S (CC: ~10분)
**Priority:** P2
**Depends on:** comprehension_checker 기본 구현 완료

## Deferred from CEO Review (2026-03-25)

- 카카오톡 어댑터 (Month 1 파일럿 후)
- SM-2 적응형 복습 알고리즘 (Phase 4)
- 학습 코치 Q&A (검증 후)
- 메모 시스템 (검증 후)
- 주간 리포트 자동화 (Phase 1.5, `/report` 수동 트리거 먼저)
- PDF 버전 관리 (문서 변경 시 개념 drift 방지)
