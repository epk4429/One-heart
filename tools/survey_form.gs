/**
 * ONE-Heart 파일럿 설문 — 구글폼 자동 생성 스크립트 (Google Apps Script)
 * 문항 기준: docs/01_파일럿_개요.md 5-A (2026-11-18 형님 확정, 같은 날 답변 방식 수정)
 *
 * 답변 방식(2026-11-18 형님 지시):
 *  - 정도를 묻는 문항은 말이 아니라 1~5 숫자로 고른다. 각 문항 설명줄에 "1 매우 불만족 · 2 불만족 · 3 보통 · 4 만족 · 5 매우 만족"을 보여 준다.
 *  - 숫자로 하기 어려운 문항(가격)은 한글 5단계(매우 비싸다~매우 싸다)로 하고, 바로 아래 이유 칸(선택)을 둔다.
 *  - 1~2점을 준 경우의 이유는 섹션마다 '이유' 칸에 적게 한다(구글폼은 숫자 문항에서 답에 따라 질문을 바꿀 수 없어서 섹션 단위).
 *
 * 사용법: https://script.google.com 에서 새 프로젝트 → 이 파일 내용을 붙여 넣기
 *        → 함수 'createSurvey' 선택 후 실행(처음 한 번 권한 허용) → 실행 로그에 폼 주소가 나옴.
 * 만들어진 폼의 '응답자에게 줄 주소'를 web/js/config.js 의 SURVEY_URL 에 넣는다.
 * 같은 스크립트를 다시 실행하면 새 폼이 또 만들어진다.
 */

var INTRO =
  'ONE-Heart 파일럿에 참여해 주셔서 감사합니다.\n\n' +
  '이 설문은 서비스를 더 좋게 만들기 위한 것으로 약 5~8분이 걸려요. ' +
  '잘한 점뿐 아니라 불편하고 아쉬웠던 점도 솔직하게 답해 주세요. ' +
  '정답은 없고, 솔직한 답이 가장 큰 도움이 됩니다.\n\n' +
  '정확히 답하기 어려운 질문은 느낀 대로 편하게 적어 주세요.\n\n' +
  '이름·연락처는 묻지 않으며, 응답은 서비스 개선에만 쓰입니다. ' +
  '가족 구성원 각자 한 번씩 답해 주세요.';

var STEPS = [
  '1. 가족방 만들기', '2. 우리 가족 이야기', '3. 각자의 생각', '4. 공동 목표 설정',
  '5. 미래 계산', '6. 합의안', '7. 상품 추천', '8. 가족 홈'
];

var LEG_SAT = '1 매우 불만족 · 2 불만족 · 3 보통 · 4 만족 · 5 매우 만족';
var LEG_REASON = '1점(매우 불만족)이나 2점(불만족)을 주신 문항이 있다면, 어떤 문항인지와 이유를 적어 주세요. (없으면 비워 두세요)';

function createSurvey() {
  var form = FormApp.create('ONE-Heart 파일럿 설문');
  form.setDescription(INTRO);
  form.setCollectEmail(false);
  // setRequireLogin / setLimitOneResponsePerUser 는 일반 구글 계정에서 '지원되지 않는 작업' 오류가 나서 뺐다(기본값이 로그인 없음·횟수 제한 없음)
  form.setAllowResponseEdits(false);
  form.setProgressBar(true);
  form.setConfirmationMessage('소중한 의견 감사합니다. 설문이 제출되었어요.');

  // ── 1. 나와 우리 가족
  form.addSectionHeaderItem().setTitle('1. 가족 정보 입력');
  choice(form, '어떤 가족으로 참여하셨나요?', ['신혼부부', '노후 준비 가족(부모 + 자녀)', '기타'], true);
  choice(form, '가족방에서 내 역할은?', ['방장(가족방을 만들었어요)', '초대받아 참여했어요'], true);
  choice(form, '연령대', ['20대', '30대', '40대', '50대', '60대', '70대 이상'], false);
  scale(form, '평소 금융(저축·대출·투자 등)이 얼마나 익숙하신가요?',
        '1 전혀 익숙하지 않다 · 2 익숙하지 않다 · 3 보통 · 4 익숙하다 · 5 매우 익숙하다',
        '전혀 익숙하지 않다', '매우 익숙하다', false);

  // ── 2. 전반적인 경험
  form.addPageBreakItem().setTitle('2. 전반적인 경험');
  satisfaction(form, '서비스 전체에 얼마나 만족하셨나요?', true);
  // 단계 다시 떠올리기(리마인드): 아래 두 문항에 답하기 전에 보여 준다
  form.addSectionHeaderItem()
      .setTitle('서비스 단계 다시 떠올려 보기')
      .setHelpText(
        '1. 가족방 만들기 — 가족방을 만들고 가족을 초대했어요\n' +
        '2. 우리 가족 이야기 — 가족의 수입·지출·자산과 목표를 입력했어요\n' +
        '3. 각자의 생각 — AI와 1:1로 대화하며 내 생각을 정리했어요\n' +
        '4. 공동 목표 설정 — AI 제안에 의견을 내고 목표 숫자를 함께 정했어요\n' +
        '5. 미래 계산 — 방법 A·B·C로 미래를 계산해 비교했어요\n' +
        '6. 합의안 — 가족이 함께 방법을 고르고 서명했어요\n' +
        '7. 상품 추천 — 목표에 맞는 상품·제도의 조건을 비교했어요\n' +
        '8. 가족 홈 — 이번 달 모은 돈과 할 일을 관리하는 화면이에요');
  satisfaction(form, '설명 없이 혼자 이해하며 쓸 수 있었던 정도에 얼마나 만족하셨나요?', true);
  form.addCheckboxItem()
      .setTitle('쓰다가 멈추고 싶거나 막막했던 단계가 있었나요? (모두 선택)')
      .setChoiceValues(STEPS.concat(['없었어요']));
  paragraph(form, '그 단계에서 어떤 점이 막막하거나 멈추고 싶었는지 적어 주세요.', false);
  paragraph(form, LEG_REASON, false);

  // ── 3. 단계별 이해
  form.addPageBreakItem().setTitle('3. 단계별 이해')
      .setHelpText('각 단계가 이해하기 쉬웠는지 골라 주세요. ' + LEG_SAT + ' · 해 보지 않은 단계는 "안 해봄"을 선택해 주세요.');
  form.addGridItem()
      .setTitle('단계별로 이해하기 쉬운 정도에 얼마나 만족하셨나요?')
      .setHelpText(LEG_SAT)
      .setRows(STEPS)
      .setColumns(['1', '2', '3', '4', '5', '안 해봄']);
  choice(form, '가장 이해하기 어려웠던 단계 하나를 고른다면?', STEPS.concat(['어려운 단계 없음']), false);
  paragraph(form, '어려웠던 이유가 있다면 적어 주세요. (1~2점을 주신 단계의 이유도 함께 적어 주세요)', false);

  // ── 4. 가족 합의에 도움
  form.addPageBreakItem().setTitle('4. 가족 합의에 도움이 되었나요?');
  satisfaction(form, '가족의 생각 중 몰랐던 것을 알게 된 점에 얼마나 만족하셨나요?', false);
  satisfaction(form, '각자 생각을 먼저 정리한 뒤 이야기하는 방식에 얼마나 만족하셨나요?', false);
  satisfaction(form, '공동 목표 설정의 결과에 얼마나 만족하셨나요?', false);
  satisfaction(form, '가족이 함께 정한 합의안에 얼마나 만족하셨나요?', false);
  satisfaction(form, '이 서비스가 가족의 합의에 도움이 된 정도에 얼마나 만족하셨나요?', false);
  // AI 제안·근거 보기는 공동 목표 설정(4단계)에서 나오므로 이 섹션에 둔다
  satisfaction(form, 'AI가 제안한 내용을 이해할 수 있었던 정도에 얼마나 만족하셨나요?', false);
  satisfaction(form, '"근거 보기"가 제안을 이해하는 데 도움이 된 정도에 얼마나 만족하셨나요? (보지 않았다면 건너뛰어 주세요)', false);
  satisfaction(form, 'AI가 대신 정하지 않고 우리 가족이 직접 결정한다고 느낀 점에 얼마나 만족하셨나요?', false);
  paragraph(form, LEG_REASON, false);

  // ── 5. 미래 계산 시뮬레이션
  form.addPageBreakItem().setTitle('5. 미래 계산 시뮬레이션');
  satisfaction(form, '미래 계산에 나온 숫자를 믿을 수 있었던 정도에 얼마나 만족하셨나요?', false);
  paragraph(form, '믿기 어려웠거나 이상했던 부분이 있었나요?', false);
  paragraph(form, LEG_REASON, false);

  // ── 6. 상품·제도 추천
  form.addPageBreakItem().setTitle('6. 상품·제도 추천');
  satisfaction(form, '상품·제도 추천이 우리 가족에게 도움이 된 정도에 얼마나 만족하셨나요?', true);
  satisfaction(form, '추천된 상품·제도가 우리 가족 상황에 맞은 정도에 얼마나 만족하셨나요?', false);
  paragraph(form, '더 알고 싶었는데 없던 정보가 있었나요?', false);
  paragraph(form, LEG_REASON, false);

  // ── 7. 입력한 정보
  form.addPageBreakItem().setTitle('7. 입력한 정보');
  form.addCheckboxItem()
      .setTitle('입력하기 꺼려졌던 항목이 있었나요? (모두 선택)')
      .setChoiceValues(['소득', '자산', '대출', '가족 간 의견·갈등', '꺼려진 항목 없음', '기타']);
  satisfaction(form, '내 생각이 가족에게 공유되는 방식(AI가 정리하고 내가 확인한 요약만 공유)에 얼마나 만족하셨나요?', false);
  paragraph(form, LEG_REASON, false);

  // ── 8. 앞으로
  form.addPageBreakItem().setTitle('8. 앞으로');
  scale(form, '이 서비스를 다시 쓰고 싶은 정도는 어떤가요?',
        '1 전혀 쓰고 싶지 않다 · 2 쓰고 싶지 않다 · 3 보통 · 4 쓰고 싶다 · 5 꼭 쓰고 싶다',
        '전혀 쓰고 싶지 않다', '꼭 쓰고 싶다', false);
  form.addScaleItem()
      .setTitle('주변 사람에게 이 서비스를 추천할 의향은?')
      .setHelpText('0 전혀 없다 ~ 10 꼭 추천하고 싶다')
      .setBounds(0, 10).setLabels('전혀 없다', '꼭 추천');
  form.addCheckboxItem()
      .setTitle('가장 쓸모 있었던 기능은? (1~2개 선택)')
      .setChoiceValues(STEPS.concat(['재점검', '해당 없음']))
      .setValidation(FormApp.createCheckboxValidation().requireSelectAtMost(2).build());

  // 가격: 한글 5단계. 화면 이동(분기) 없이 같은 화면에 이유 칸을 둔다
  choice(form,
    '합의안과 상품·제도 추천을 포함한 결과 리포트와 지속적인 관리를 도와주는 가족 홈 대시보드를 1회 2,900원에 이용한다면, 가격은 어떤가요?',
    ['매우 비싸다', '비싸다', '적당하다', '싸다', '매우 싸다'], false);
  paragraph(form, '"매우 비싸다" 또는 "비싸다"를 고르셨다면 이유를 적어 주세요. (아니면 비워 두세요)', false);

  // ── 9. 마무리
  form.addPageBreakItem().setTitle('9. 마무리');
  paragraph(form, '가장 좋았던 점은 무엇인가요?', false);
  paragraph(form, '가장 아쉬웠던 점은 무엇인가요?', false);

  Logger.log('편집 주소: ' + form.getEditUrl());
  Logger.log('응답자에게 줄 주소(SURVEY_URL에 넣기): ' + form.getPublishedUrl());
}

function choice(form, title, options, required) {
  form.addMultipleChoiceItem().setTitle(title).setChoiceValues(options).setRequired(required);
}

// 만족도 문항: 1~5 숫자, 설명줄에 전체 뜻을 보여 준다
function satisfaction(form, title, required) {
  scale(form, title, LEG_SAT, '매우 불만족', '매우 만족', required);
}

function scale(form, title, legend, low, high, required) {
  form.addScaleItem().setTitle(title).setHelpText(legend)
      .setBounds(1, 5).setLabels(low, high).setRequired(required);
}

function paragraph(form, title, required) {
  form.addParagraphTextItem().setTitle(title).setRequired(required);
}
