/**
 * 산출물 끝 안내 설정 읽기 — docx 없이 Node 만으로 돈다(테스트가 이 파일만 부른다).
 * 정본: references/cta-config.md — 유의사항 문장 1개, 상담 안내는 사용 변호사의 사무소 정보 파일이 있을 때만.
 */
const fs = require('fs');
const os = require('os');
const path = require('path');

const CONFIG = path.join(__dirname, '..', '..', '..', 'references', 'cta-config.md');

// cta-config.md 「유의사항 문장」 절의 코드 블록 첫 줄
function notice(configPath = CONFIG) {
  const text = fs.readFileSync(configPath, 'utf8');
  const m = text.match(/## 유의사항 문장[\s\S]*?```\n([^\n]+)\n```/);
  if (!m) throw new Error('cta-config.md 에서 유의사항 문장을 찾지 못했습니다');
  return m[1].trim();
}

function officeFile() {
  if (process.env.LAWFIRM_OFFICE_FILE) return process.env.LAWFIRM_OFFICE_FILE;
  if (process.platform === 'win32') {
    const base = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local');
    return path.join(base, 'intent-brief', 'office.json');
  }
  return path.join(os.homedir(), '.intent-brief', 'office.json');
}

// 사무소 정보 — 파일이 없거나 이름이 없으면 null(상담 안내를 붙이지 않는다)
function loadOffice(file = officeFile()) {
  let o;
  try {
    o = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
  if (!o || typeof o !== 'object' || !String(o.name || '').trim()) return null;
  const s = (v) => (v === undefined || v === null ? '' : String(v).trim());
  return { name: s(o.name), title: s(o.title) || '변호사', phone: s(o.phone), email: s(o.email), website: s(o.website) };
}

module.exports = { notice, loadOffice, officeFile };
