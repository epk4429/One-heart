/**
 * ONE-Heart 파일럿 설문 — 구글폼 자동 생성 스크립트 (Google Apps Script)
 * 문항 기준: docs/01_파일럿_개요.md 5-A (2026-11-19 형님 요청으로 간단 버전으로 다시 씀)
 *
 * 취합 목적: 만족도 / 재방문(재사용) / 개선할 점. (합의안 생성률은 설문이 아니라 사용 기록으로 센다)
 * 구성: 가족 정보 4문항(원래대로) → 만족도 5문항 → 기능성 5문항(각각 1~5 척도 문항) → 가격 1문항 + 개선할 점 1문항(복수 선택) + 한마디(선택).
 *       약 2분, 서술형은 선택 1개뿐이라 발표자료에 숫자로 바로 정리할 수 있다.
 *
 * 사용법: https://script.google.com 에서 새 프로젝트 → 이 파일 내용을 붙여 넣기
 *        → 함수 'createSurvey' 선택 후 실행(처음 한 번 권한 허용) → 실행 로그에 폼 주소가 나옴.
 * 만들어진 폼의 '응답자에게 줄 주소'를 web/js/config.js 의 SURVEY_URL 에 넣는다.
 * 같은 스크립트를 다시 실행하면 새 폼이 또 만들어진다(예전 폼은 직접 지우기).
 */

var INTRO =
  'ONE-Heart 파일럿에 참여해 주셔서 감사합니다.\n\n' +
  '2분이면 끝나는 짧은 설문이에요. 잘한 점뿐 아니라 아쉬웠던 점도 솔직하게 골라 주세요.\n\n' +
  '이름·연락처는 묻지 않으며, 응답은 서비스 개선에만 쓰입니다. ' +
  '가족 구성원 각자 한 번씩 답해 주세요.';

var LEG_SAT = '1 매우 불만족 · 2 불만족 · 3 보통 · 4 만족 · 5 매우 만족';
var LEG_AGREE = '1 전혀 그렇지 않다 · 2 그렇지 않다 · 3 보통 · 4 그렇다 · 5 매우 그렇다';

function createSurvey() {
  var form = FormApp.create('ONE-Heart 파일럿 설문');
  form.setDescription(INTRO);
  form.setCollectEmail(false);
  // setRequireLogin / setLimitOneResponsePerUser 는 일반 구글 계정에서 '지원되지 않는 작업' 오류가 나서 뺐다
  form.setAllowResponseEdits(false);
  form.setProgressBar(true);
  form.setConfirmationMessage('소중한 의견 감사합니다. 설문이 제출되었어요.');

  // ── 1. 가족 정보 입력 (원래 문항 그대로)
  form.addSectionHeaderItem().setTitle('1. 가족 정보 입력');
  choice(form, '어떤 가족으로 참여하셨나요?', ['신혼부부', '노후 준비 가족(부모 + 자녀)', '기타'], true);
  choice(form, '가족방에서 내 역할은?', ['방장(가족방을 만들었어요)', '초대받아 참여했어요'], true);
  choice(form, '연령대', ['20대', '30대', '40대', '50대', '60대', '70대 이상'], false);
  form.addScaleItem().setTitle('평소 금융(저축·대출·투자 등)이 얼마나 익숙하신가요?')
      .setHelpText('1 전혀 익숙하지 않다 · 2 익숙하지 않다 · 3 보통 · 4 익숙하다 · 5 매우 익숙하다')
      .setBounds(1, 5).setLabels('전혀 익숙하지 않다', '매우 익숙하다').setRequired(false);

  // ── 2. 만족도 (5문항) — 재사용 의향이 재방문 지표
  form.addPageBreakItem().setTitle('2. 만족도').setHelpText(LEG_SAT);
  // 표(그리드)는 왼쪽 글자 칸 폭을 못 바꿔 줄바꿈이 심해서, 문항마다 1~5 척도로 둔다(2026-11-19)
  form.addSectionHeaderItem().setTitle('ONE-Heart가 주는 가치에 얼마나 만족하셨나요?');
  satisfaction(form, '서비스 전체');
  satisfaction(form, '가족의 서로 다른 생각을 알고 이해하게 된 것');
  satisfaction(form, '가족 모두가 납득하는 공동 목표를 정한 것');
  satisfaction(form, '같은 미래를 바라보는 하나의 합의안을 만든 것');
  satisfaction(form, '다음에도 이 서비스를 쓰고 싶은 정도');

  // ── 3. 기능성 (5문항)
  form.addPageBreakItem().setTitle('3. 기능').setHelpText(LEG_AGREE);
  form.addSectionHeaderItem().setTitle('다음 설명이 얼마나 맞나요?');
  agree(form, '설명 없이도 혼자 이해하며 쓸 수 있었다');
  agree(form, 'AI 제안과 그 근거를 이해할 수 있었다');
  agree(form, '미래 계산 결과를 믿을 수 있었다');
  agree(form, '상품·제도 비교가 우리 가족에게 도움이 되었다');
  agree(form, '이 서비스가 가족의 합의에 도움이 되었다');

  // ── 4. 가격 + 개선할 점 (객관식 2 + 선택 한마디 1)
  form.addPageBreakItem().setTitle('4. 가격과 개선할 점');
  choice(form,
    '합의안과 상품·제도 추천을 포함한 결과 리포트와 지속적인 관리를 도와주는 가족 홈 대시보드를 1회 2,900원에 이용한다면, 가격은 어떤가요?',
    ['매우 비싸다', '비싸다', '적당하다', '싸다', '매우 싸다'], true);
  form.addCheckboxItem()
      .setTitle('고쳐졌으면 하는 점은 무엇인가요? (모두 선택)')
      .setChoiceValues([
        '입력할 것이 많고 번거로워요',
        '용어·설명이 어려워요',
        'AI 제안이 와닿지 않아요',
        '미래 계산 숫자가 이해·신뢰되지 않아요',
        '상품·제도 정보가 부족해요',
        '화면 사용법이 헷갈려요',
        '느리거나 오류가 있었어요',
        '고칠 점이 없어요'
      ])
      .setRequired(true);
  paragraph(form, '그 밖에 하고 싶은 말이 있다면 한 줄만 적어 주세요. (선택)', false);

  Logger.log('편집 주소: ' + form.getEditUrl());
  Logger.log('응답자에게 줄 주소(SURVEY_URL에 넣기): ' + form.getPublishedUrl());
}

function choice(form, title, options, required) {
  form.addMultipleChoiceItem().setTitle(title).setChoiceValues(options).setRequired(required);
}

// 1~5 척도 문항(필수). 양 끝 이름이 보여서 숫자 뜻을 따로 안 적어도 된다
function satisfaction(form, title) {
  form.addScaleItem().setTitle(title).setBounds(1, 5).setLabels('매우 불만족', '매우 만족').setRequired(true);
}

function agree(form, title) {
  form.addScaleItem().setTitle(title).setBounds(1, 5).setLabels('전혀 그렇지 않다', '매우 그렇다').setRequired(true);
}

function paragraph(form, title, required) {
  form.addParagraphTextItem().setTitle(title).setRequired(required);
}
