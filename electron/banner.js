function printBanner() {
  const p = '\x1b[35m';   // purple
  const b = '\x1b[1m';    // bold
  const d = '\x1b[2m';    // dim
  const c = '\x1b[36m';   // cyan
  const g = '\x1b[90m';   // gray
  const w = '\x1b[37m';   // white
  const r = '\x1b[0m';    // reset
  const gr = '\x1b[32m';  // green

  console.log('');
  console.log(g + '  ┌─────────────────────────────────────────────┐' + r);
  console.log(g + '  │                                             │' + r);
  console.log(g + '  │' + b + p + '   ███████  █████  ██       █████  ████   ' + r + g + '│' + r);
  console.log(g + '  │' + b + p + '   ██      ██   ██ ██      ██   ██ ██  ██ ' + r + g + '│' + r);
  console.log(g + '  │' + b + p + '   ███████ ███████ ██      ███████ ██  ██ ' + r + g + '│' + r);
  console.log(g + '  │' + b + p + '        ██ ██   ██ ██      ██   ██ ██  ██ ' + r + g + '│' + r);
  console.log(g + '  │' + b + p + '   ███████ ██   ██ ███████ ██   ██ ████   ' + r + g + '│' + r);
  console.log(g + '  │' + r + '                                             ' + g + '│' + r);
  console.log(g + '  │' + b + c + '              ██████   ██████  ██   ██    ' + r + g + '│' + r);
  console.log(g + '  │' + b + c + '              ██   ██ ██    ██  ██ ██     ' + r + g + '│' + r);
  console.log(g + '  │' + b + c + '              ██████  ██    ██   ███      ' + r + g + '│' + r);
  console.log(g + '  │' + b + c + '              ██   ██ ██    ██  ██ ██     ' + r + g + '│' + r);
  console.log(g + '  │' + b + c + '              ██████   ██████  ██   ██    ' + r + g + '│' + r);
  console.log(g + '  │                                             │' + r);
  console.log(g + '  └─────────────────────────────────────────────┘' + r);
  console.log('');
}

function printSection(title) {
  const c = '\x1b[36m';
  const b = '\x1b[1m';
  const g = '\x1b[90m';
  const r = '\x1b[0m';

  console.log('');
  console.log(g + '  ──────────────────────────────────────────────' + r);
  console.log(b + c + '  ' + title + r);
  console.log(g + '  ──────────────────────────────────────────────' + r);
}

function printStatus(label, value, status = 'info') {
  const colors = {
    success: '\x1b[32m',
    warning: '\x1b[33m',
    error: '\x1b[31m',
    info: '\x1b[36m',
  };

  const g = '\x1b[90m';
  const r = '\x1b[0m';
  const sc = colors[status] || colors.info;

  console.log(g + '  │ ' + r + sc + label + r + ' ' + value);
}

module.exports = {
  printBanner,
  printSection,
  printStatus,
};
