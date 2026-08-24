// Shared site chrome. Light is the default; an explicit visitor choice wins.
let selectedTheme = window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
try {
  const savedTheme = localStorage.getItem('gradiated-theme');
  if (savedTheme === 'dark' || savedTheme === 'light') selectedTheme = savedTheme;
} catch {}
document.documentElement.dataset.theme = selectedTheme;

const palette = document.createElement('link');
palette.rel = 'stylesheet';
palette.href = '/palette.css';
document.head.append(palette);

const footerStyles = document.createElement('link');
footerStyles.rel = 'stylesheet';
footerStyles.href = '/footer.css';
document.head.append(footerStyles);

const articleStyles = document.createElement('link');
articleStyles.rel = 'stylesheet';
articleStyles.href = '/article.css';
document.head.append(articleStyles);

let socraticStyles = document.querySelector('link[href="/socratic.css"]');
if (!socraticStyles) {
  socraticStyles = document.createElement('link');
  socraticStyles.rel = 'stylesheet';
  socraticStyles.href = '/socratic.css';
}
// Keep the new system last in the cascade, after the legacy shared styles.
document.head.append(socraticStyles);

// Exact transparent logo variants for browser chrome.
const favicon = document.createElement('link');
favicon.rel = 'icon';
favicon.type = 'image/png';
document.head.append(favicon);

const appleTouchIcon = document.createElement('link');
appleTouchIcon.rel = 'apple-touch-icon';
appleTouchIcon.href = '/gradiated-logo-dark-exact.png';
document.head.append(appleTouchIcon);

const header = document.querySelector('header.nav');
if (header) {
  const path = location.pathname;
  const active = path.startsWith('/products') ? 'products' : path.startsWith('/library') || path.startsWith('/notes') ? 'library' : 'home';
  header.innerHTML = `
    <a class="wordmark" href="/" aria-label="Gradiated home"><img class="wordmark-logo" src="/gradiated-logo-dark-exact.png" alt="" width="25" height="25">gradiated</a>
    <nav>
      <a class="${active === 'home' ? 'active' : ''}" href="/">Home</a>
      <a class="${active === 'products' ? 'active' : ''}" href="/products/">Products</a>
      <a class="${active === 'library' ? 'active' : ''}" href="/library/">Library</a>
    </nav>`;
}

const themeToggle = document.createElement('button');
themeToggle.className = 'theme-toggle';
themeToggle.type = 'button';
(document.querySelector('footer') || document.body).append(themeToggle);
const wordmarkLogo = document.querySelector('.wordmark-logo');

function applyTheme(theme) {
  const dark = theme === 'dark';
  document.documentElement.dataset.theme = theme;
  if (wordmarkLogo) wordmarkLogo.src = dark ? '/gradiated-logo-light-exact.png' : '/gradiated-logo-dark-exact.png';
  favicon.href = dark ? '/gradiated-logo-light-exact.png' : '/gradiated-logo-dark-exact.png';
  if (themeToggle) {
    const alternative = dark ? 'light' : 'dark';
    themeToggle.innerHTML = `<span class="theme-question">${dark ? 'Light' : 'Dark'}<i>?</i></span><span class="theme-consider" aria-hidden="true">Consider ${alternative} →</span>`;
    themeToggle.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
    themeToggle.setAttribute('aria-pressed', String(dark));
  }
}

applyTheme(selectedTheme);
themeToggle?.addEventListener('click', () => {
  selectedTheme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(selectedTheme);
  try { localStorage.setItem('gradiated-theme', selectedTheme); } catch {}
});

document.querySelectorAll('a[href^="mailto:"]').forEach((link) => {
  link.href = link.href.replace(/mailto:[^?]+/, 'mailto:signal@gradiated.com');
});
const emailText = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
while (emailText.nextNode()) {
  const node = emailText.currentNode;
  if (!['SCRIPT', 'STYLE'].includes(node.parentElement?.tagName)) node.textContent = node.textContent.replace(/hello@gradiated\.com/g, 'signal@gradiated.com');
}

document.querySelector('.notes > .eyebrow')?.remove();
const articleBackLink = document.querySelector('.article > .eyebrow[href="/notes/"]');
if (articleBackLink) {
  articleBackLink.href = '/library/';
  articleBackLink.textContent = '← Library';
}

// A short Socratic intake for the existing email-based waitlist.
const waitlistDialog = document.createElement('dialog');
waitlistDialog.className = 'waitlist-dialog';
waitlistDialog.setAttribute('aria-labelledby', 'waitlist-question');
waitlistDialog.innerHTML = `
  <form class="waitlist-inquiry">
    <button class="waitlist-close" type="button" aria-label="Close waitlist inquiry">Close ×</button>
    <div class="waitlist-progress" aria-hidden="true"><i></i></div>
    <section class="waitlist-step is-active" data-step="1">
      <p class="waitlist-count">Question 01 / 02</p>
      <h2 id="waitlist-question">Which inference trade-offs matter to you?</h2>
      <p class="waitlist-guidance">Select one or more.</p>
      <div class="waitlist-options" data-options="question">
        <button type="button" aria-pressed="false" data-value="Cost">Cost</button>
        <button type="button" aria-pressed="false" data-value="Quality">Quality</button>
        <button type="button" aria-pressed="false" data-value="Latency">Latency</button>
        <button type="button" aria-pressed="false" data-value="Configurability">Configurability</button>
      </div>
      <button class="waitlist-next" type="button" disabled>Continue →</button>
    </section>
    <section class="waitlist-step" data-step="2">
      <p class="waitlist-count">Question 02 / 02</p>
      <h2>Which best describes you?</h2>
      <p class="waitlist-guidance">Choose the closest fit.</p>
      <div class="waitlist-options" data-options="identity">
        <button type="button" aria-pressed="false" data-value="Developer">Developer</button>
        <button type="button" aria-pressed="false" data-value="Researcher">Researcher</button>
        <button type="button" aria-pressed="false" data-value="Founder">Founder</button>
        <button type="button" aria-pressed="false" data-value="Infrastructure team">Infrastructure team</button>
        <button type="button" aria-pressed="false" data-value="Other">Other</button>
      </div>
      <label class="waitlist-email">Where should we continue the conversation?<span><input type="email" name="email" autocomplete="email" placeholder="you@company.com" required><i class="waitlist-email-error" aria-live="polite"></i></span></label>
      <div class="waitlist-actions"><button class="waitlist-back" type="button">← Back</button><button class="waitlist-submit" type="submit" disabled>Join waitlist →</button></div>
    </section>
    <a class="waitlist-skip" href="mailto:signal@gradiated.com?subject=Waitlist">Skip the questions — email us directly</a>
  </form>`;
document.body.append(waitlistDialog);

const inquiryState = { questions: [], identity: '' };
const stepOne = waitlistDialog.querySelector('[data-step="1"]');
const stepTwo = waitlistDialog.querySelector('[data-step="2"]');
const inquiryProgress = waitlistDialog.querySelector('.waitlist-progress i');
const nextQuestion = waitlistDialog.querySelector('.waitlist-next');
const inquiryEmail = waitlistDialog.querySelector('input[type="email"]');
const inquirySubmit = waitlistDialog.querySelector('.waitlist-submit');

function showInquiryStep(step) {
  stepOne.classList.toggle('is-active', step === 1);
  stepTwo.classList.toggle('is-active', step === 2);
  inquiryProgress.style.width = step === 1 ? '50%' : '100%';
  if (step === 2) inquiryEmail.focus();
}

waitlistDialog.querySelectorAll('[data-options] button').forEach((option) => {
  option.addEventListener('click', () => {
    const group = option.closest('[data-options]').dataset.options;
    if (group === 'question') {
      option.setAttribute('aria-pressed', String(option.getAttribute('aria-pressed') !== 'true'));
      inquiryState.questions = [...waitlistDialog.querySelectorAll('[data-options="question"] [aria-pressed="true"]')].map(item => item.dataset.value);
      nextQuestion.disabled = inquiryState.questions.length === 0;
    } else {
      waitlistDialog.querySelectorAll('[data-options="identity"] button').forEach(item => item.setAttribute('aria-pressed', 'false'));
      option.setAttribute('aria-pressed', 'true');
      inquiryState.identity = option.dataset.value;
    }
    inquirySubmit.disabled = !(inquiryState.identity && inquiryEmail.validity.valid);
  });
});

inquiryEmail.addEventListener('input', () => {
  inquirySubmit.disabled = !(inquiryState.identity && inquiryEmail.validity.valid);
  waitlistDialog.querySelector('.waitlist-email-error').textContent = '';
});
inquiryEmail.addEventListener('blur', () => {
  waitlistDialog.querySelector('.waitlist-email-error').textContent = inquiryEmail.value && !inquiryEmail.validity.valid ? 'Is that a complete email address?' : '';
});
nextQuestion.addEventListener('click', () => showInquiryStep(2));
waitlistDialog.querySelector('.waitlist-back').addEventListener('click', () => showInquiryStep(1));
waitlistDialog.querySelector('.waitlist-close').addEventListener('click', () => waitlistDialog.close());
waitlistDialog.addEventListener('click', (event) => { if (event.target === waitlistDialog) waitlistDialog.close(); });
waitlistDialog.querySelector('form').addEventListener('submit', (event) => {
  event.preventDefault();
  const body = `Questioning: ${inquiryState.questions.join(', ')}\nWho is asking: ${inquiryState.identity}\nEmail: ${inquiryEmail.value}`;
  location.href = `mailto:signal@gradiated.com?subject=Waitlist&body=${encodeURIComponent(body)}`;
});

document.querySelectorAll('a[href*="subject=Waitlist"]:not(.waitlist-skip)').forEach((link) => {
  link.addEventListener('click', (event) => {
    event.preventDefault();
    showInquiryStep(1);
    waitlistDialog.showModal();
    waitlistDialog.querySelector('[data-options="question"] button').focus();
  });
});
