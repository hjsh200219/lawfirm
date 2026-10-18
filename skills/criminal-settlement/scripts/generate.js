#!/usr/bin/env node
/**
 * 형사 합의서 생성 스크립트
 * Usage: node generate.js --data "<JSON 파일 경로>" --output "<path>"  (사용자 입력 JSON 을 셸 인자에 직접 넣지 않는다)
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType
} = require('docx');
const fs = require('fs');

// ── 산출물 끝 안내 (정본 references/cta-config.md — 상담 안내는 사무소 정보 파일이 있을 때만) ──
const cta = require('./cta');
const NOTICE = cta.notice();
const OFFICE = cta.loadOffice();
const DOC_TYPE = '형사 합의서';

// ── 인자 파싱 ─────────────────────────────────────────────────
const args = process.argv.slice(2);
let dataJson = '', outputPath = '형사합의서.docx'; // 기본: 현재 작업 폴더
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--data') dataJson = args[i + 1];
  if (args[i] === '--output') outputPath = args[i + 1];
}

// 인라인 JSON 또는 파일 경로 지원
let d;
try {
  d = JSON.parse(dataJson);
} catch {
  try {
    d = JSON.parse(fs.readFileSync(dataJson, 'utf8'));
  } catch {
    console.error('❌ --data 파싱 실패. JSON 문자열 또는 파일 경로를 입력하세요.');
    process.exit(1);
  }
}

// ── 스타일 헬퍼 ───────────────────────────────────────────────
const FONT = "맑은 고딕";
const cellBorder = { style: BorderStyle.SINGLE, size: 1, color: "999999" };
const borders = { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder };
const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

// ── 한글 원 숫자 ─────────────────────────────────────────────
const circleNums = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩','⑪','⑫','⑬','⑭','⑮'];
function circleNum(idx) {
  return circleNums[idx] || `(${idx + 1})`;
}

function t(text, opts = {}) {
  return new TextRun({ text: String(text), font: FONT, size: 22, ...opts });
}
function para(children, opts = {}) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    ...opts,
    children: Array.isArray(children) ? children : [t(children, opts.run || {})]
  });
}
function title(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 400, after: 200 },
    children: [t(text, { bold: true, size: 36 })]
  });
}
function subtitle(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 300 },
    children: [t(text, { size: 22 })]
  });
}
function sectionTitle(text) {
  return new Paragraph({
    spacing: { before: 280, after: 120 },
    children: [t(text, { bold: true, size: 24 })]
  });
}
function clause(num, text) {
  return new Paragraph({
    spacing: { before: 100, after: 80 },
    indent: { left: 200 },
    children: [t(`${num} ${text}`)]
  });
}
function hrule() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "333333", space: 1 } },
    spacing: { before: 200, after: 200 },
    children: []
  });
}
function infoTable(rows) {
  return new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [2200, 6826],
    rows: rows.map(([label, val]) => new TableRow({
      children: [
        new TableCell({
          borders, width: { size: 2200, type: WidthType.DXA },
          shading: { fill: "F2F2F2", type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [para([t(label, { bold: true })])]
        }),
        new TableCell({
          borders, width: { size: 6826, type: WidthType.DXA },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [para(val)]
        }),
      ]
    }))
  });
}

// ── 분할지급 일정표 ─────────────────────────────────────────────
function installmentTable(installments) {
  const headerRow = new TableRow({
    children: ['회차', '지급금액', '지급기한'].map(label =>
      new TableCell({
        borders,
        shading: { fill: "F2F2F2", type: ShadingType.CLEAR },
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [t(label, { bold: true })] })]
      })
    )
  });

  const dataRows = installments.map((item, idx) =>
    new TableRow({
      children: [
        new TableCell({
          borders,
          margins: { top: 60, bottom: 60, left: 100, right: 100 },
          children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [t(`${idx + 1}회`)] })]
        }),
        new TableCell({
          borders,
          margins: { top: 60, bottom: 60, left: 100, right: 100 },
          children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [t(item.금액)] })]
        }),
        new TableCell({
          borders,
          margins: { top: 60, bottom: 60, left: 100, right: 100 },
          children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [t(item.기한)] })]
        }),
      ]
    })
  );

  return new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [1800, 3613, 3613],
    rows: [headerRow, ...dataRows]
  });
}

function signatureTable(피해자, 가해자) {
  function sigCell(role, person) {
    return new TableCell({
      borders: noBorders,
      width: { size: 4513, type: WidthType.DXA },
      margins: { top: 120, bottom: 120, left: 200, right: 200 },
      children: [
        new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 },
          children: [t(role, { bold: true })] }),
        new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 },
          children: [t(`성  명: ${person.name}    (인)`)] }),
        new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 },
          children: [t(`주  소: ${person.address}`)] }),
        new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 },
          children: [t(`생년월일: ${person.dob}`)] }),
      ]
    });
  }
  return new Table({
    width: { size: 9026, type: WidthType.DXA },
    columnWidths: [4513, 4513],
    rows: [new TableRow({ children: [sigCell("피해자 (갑)", 피해자), sigCell("가해자 (을)", 가해자)] })]
  });
}

// ── 금액 텍스트 중복 "금" 방지 헬퍼 ────────────────────────────
function formatAmount(한글, 숫자) {
  const cleanHangul = 한글.replace(/^금\s*/, '').trim();
  return `금 ${cleanHangul} 원(${숫자})`;
}

// ── 합의 내용 조항 생성 (동적 번호) ─────────────────────────────
function buildClauses(d) {
  const 특약 = d.특약 || {};
  const clauses = [];
  let idx = 0; // 동적 번호 인덱스

  // 합의금
  const 금액숫자 = d.합의금 ? `₩${d.합의금}` : '○○○원';
  const 금액한글 = d.합의금한글 || '○○';
  const 지급방법 = d.지급방법 || '계좌이체';
  const 계좌 = d.계좌정보 ? `갑의 계좌(${d.계좌정보})로` : '갑이 지정하는 계좌로';

  // 분할지급 여부 확인
  const 분할지급 = d.분할지급 && Array.isArray(d.분할지급) && d.분할지급.length > 0;

  if (분할지급) {
    clauses.push(clause(circleNum(idx++),
      `(합의금) 을은 갑에게 합의금으로 ${formatAmount(금액한글, 금액숫자)}을 아래 일정에 따라 분할 지급하기로 합니다.`));
    clauses.push(installmentTable(d.분할지급));
    if (d.계좌정보) {
      clauses.push(para(`   지급계좌: ${d.계좌정보}`));
    }
  } else {
    clauses.push(clause(circleNum(idx++),
      `(합의금) 을은 갑에게 합의금으로 ${formatAmount(금액한글, 금액숫자)}을 ${d.지급기한 || '○○○○. ○○. ○○.'}까지 ${계좌} ${지급방법}하기로 합니다.`));
  }

  // 고소 취하
  if (특약.고소취하 !== false) {
    const 사건번호 = d.고소사건번호 ? `(${d.고소사건번호})` : '';
    if (분할지급) {
      clauses.push(clause(circleNum(idx++),
        `(고소 취하) 갑은 을이 위 합의금 전액을 지급 완료함과 동시에 을에 대하여 제기한 고소${사건번호}를 취하하기로 합니다.`));
    } else {
      clauses.push(clause(circleNum(idx++),
        `(고소 취하) 갑은 위 합의금을 수령함과 동시에 을에 대하여 제기한 고소${사건번호}를 취하하기로 합니다.`));
    }
  }

  // 처벌불원
  if (특약.처벌불원 !== false) {
    clauses.push(clause(circleNum(idx++),
      `(처벌불원) 갑은 을에 대하여 처벌을 원하지 아니하며, 향후 이 사건과 관련하여 민·형사상 어떠한 이의도 제기하지 않을 것을 확약합니다.`));
  }

  // 접근금지
  if (특약.접근금지) {
    clauses.push(clause(circleNum(idx++),
      `(접근금지) 을은 향후 갑 및 갑의 가족, 지인에게 어떠한 형태로도 접근하거나 연락하지 않을 것을 약속합니다.`));
  }

  // 게시물 삭제
  if (특약.게시물삭제) {
    clauses.push(clause(circleNum(idx++),
      `(게시물 삭제) 을은 본 합의서 작성일로부터 24시간 이내에 위 게시물 및 관련 댓글 일체를 삭제하고, 이를 갑에게 증빙하기로 합니다.`));
  }

  // 공개 사과
  if (특약.공개사과) {
    clauses.push(clause(circleNum(idx++),
      `(공개 사과) 을은 갑이 지정하는 방식으로 사과문을 게재하기로 합니다. 사과문의 내용 및 게재 방법은 갑과 을이 별도로 협의합니다.`));
  }

  // 추가 게시 금지
  if (특약.추가게시금지) {
    clauses.push(clause(circleNum(idx++),
      `(추가 게시 금지) 을은 향후 갑에 관한 허위 사실 또는 비방 내용을 온·오프라인을 불문하고 일체 유포하지 아니하기로 합니다.`));
  }

  // 위약금 (중복 "금" 방지)
  if (특약.위약금 && 특약.위약금액) {
    const cleanAmt = 특약.위약금액.replace(/^금\s*/, '').trim();
    clauses.push(clause(circleNum(idx++),
      `(위약금) 을이 위 합의 내용을 위반할 경우, 을은 갑에게 위약금으로 금 ${cleanAmt}을 즉시 지급하기로 합니다.`));
  }

  // 기한이익 상실 (분할지급 시 자동 추가)
  if (분할지급 && 특약.기한이익상실 !== false) {
    clauses.push(clause(circleNum(idx++),
      `(기한이익 상실) 을이 위 분할금 중 1회라도 지급기일을 도과할 경우, 을은 나머지 잔액 전부에 대한 기한의 이익을 상실하며, 갑은 즉시 잔액 전액의 지급을 청구할 수 있습니다.`));
  }

  // 합의금 미지급 시 효력 상실
  if (특약.합의금미지급효력상실) {
    clauses.push(clause(circleNum(idx++),
      `(효력 상실) 을이 위 합의금을 약정 기일 내에 지급하지 아니할 경우 본 합의서는 효력을 잃으며, 갑은 고소를 재개할 수 있습니다.`));
  }

  // 기타 특약
  if (특약.기타) {
    clauses.push(clause(circleNum(idx++), `(기타) ${특약.기타}`));
  }

  return clauses;
}

// ── 사건 유형 부제목 ─────────────────────────────────────────
function getSubtitle(유형) {
  const map = {
    '상해·폭행': '상해 사건',
    '재물손괴': '재물손괴 사건',
    '명예훼손': '정보통신망 이용 명예훼손 사건',
    '사기·횡령': '사기 사건',
    '사기': '사기 사건',
    '횡령': '횡령 사건',
    '교통사고': '교통사고 사건',
    '성범죄': '형사 사건',
  };
  return map[유형] || (유형 ? `${유형} 사건` : '형사 사건');
}

// ── 문서 생성 (사건개요 섹션 제거) ──────────────────────────────
const children = [
  title("합  의  서"),
  subtitle(`(${getSubtitle(d.사건유형)})`),
  hrule(),

  // 1. 당사자
  sectionTitle("1. 당사자 표시"),
  infoTable([
    ["피  해  자 (갑)", `성명: ${d.피해자?.name || '○○○'} / 생년월일: ${d.피해자?.dob || '○○○○. ○○. ○○.'}`],
    ["가  해  자 (을)", `성명: ${d.가해자?.name || '○○○'} / 생년월일: ${d.가해자?.dob || '○○○○. ○○. ○○.'}`],
  ]),

  // 2. 합의 내용 (사건개요 제거, 바로 합의 내용)
  sectionTitle("2. 합의 내용"),
  ...buildClauses(d),

  // 작성일
  sectionTitle("3. 작성일"),
  para(d.작성일 || '○○○○년 ○○월 ○○일'),
  hrule(),
  para([t("위 합의 내용을 확인하고 이에 서명·날인합니다.", { bold: true })]),
  new Paragraph({ spacing: { before: 300, after: 300 }, children: [] }),
  signatureTable(
    { name: d.피해자?.name || '○○○', dob: d.피해자?.dob || '○○○○. ○○. ○○.', address: d.피해자?.address || '○○' },
    { name: d.가해자?.name || '○○○', dob: d.가해자?.dob || '○○○○. ○○. ○○.', address: d.가해자?.address || '○○' }
  ),
];

// ── 유의사항·상담 안내 페이지 (별도 페이지) ──────────────────────
const center = (children, before = 60, after = 60) =>
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before, after }, children });
const rule = (size, color, before, after) =>
  new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size, color, space: 1 } }, spacing: { before, after }, children: [] });

const officeBlock = OFFICE ? [
  rule(2, "CCCCCC", 100, 300),
  center([t("[상담 안내]", { bold: true, size: 24, color: "555555" })], 200, 200),
  center([t(`${OFFICE.title} ${OFFICE.name}`, { bold: true, size: 22, color: "333333" })], 80, 60),
  ...[["전화", OFFICE.phone], ["이메일", OFFICE.email], ["홈페이지", OFFICE.website]]
    .filter(([, v]) => v)
    .map(([k, v]) => center([t(`${k}: `, { size: 20, color: "666666" }), t(v, { size: 20, color: "333333" })])),
] : [];

const disclaimerChildren = [
  new Paragraph({ spacing: { before: 600, after: 400 }, children: [] }),
  rule(6, "AAAAAA", 0, 300),
  center([t("[유의사항]", { bold: true, size: 24, color: "555555" })], 200, 200),
  center([t(NOTICE, { size: 20, color: "666666" })], 80, 200),
  ...officeBlock,
  new Paragraph({ spacing: { before: 300, after: 0 }, children: [] }),
  new Paragraph({
    border: { top: { style: BorderStyle.SINGLE, size: 2, color: "CCCCCC", space: 1 } },
    spacing: { before: 200, after: 0 },
    children: []
  }),
  center([t(`※  본 안내는 ${DOC_TYPE} 본문이 아닙니다. 법원/기관 제출 시 본 페이지는 제외하십시오.`, { size: 18, color: "999999", italics: true })], 120, 80),
];

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: 22 } } } },
  sections: [
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      children
    },
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      children: disclaimerChildren
    }
  ]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(outputPath, buf);
  console.log(`✅ 합의서 생성 완료: ${outputPath}`);
}).catch(err => {
  console.error('❌ 생성 실패:', err.message);
  process.exit(1);
});
