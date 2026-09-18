(function () {
  const checks = {
    required: (value) => value.trim().length > 0,
    email: (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim()),
    minlength: (value, param) => value.trim().length >= Number(param),
    maxlength: (value, param) => value.trim().length <= Number(param),
  };

  const messages = {
    required: () => 'This field is required.',
    email: () => 'Enter a valid email address.',
    minlength: (param) => `Must be at least ${param} characters long.`,
    maxlength: (param) => `Must be at most ${param} characters long.`,
  };

  function parseRules(spec) {
    return spec.split(',').map((rule) => {
      const [name, param] = rule.split(':');
      return { name, param };
    });
  }

  function validateField(input) {
    const spec = input.dataset.rules;
    const errorEl = document.getElementById(`${input.id}-error`);
    if (!spec || !errorEl) return true;

    const value = input.value;
    for (const { name, param } of parseRules(spec)) {
      const check = checks[name];
      if (check && !check(value, param)) {
        errorEl.textContent = messages[name](param);
        return false;
      }
    }
    errorEl.textContent = '';
    return true;
  }

  document.querySelectorAll('input[data-rules]').forEach((input) => {
    // Only start showing/clearing live errors once the user has interacted
    // with the field (blur), so a fresh form isn't red before they type.
    let touched = false;
    input.addEventListener('blur', () => {
      touched = true;
      validateField(input);
    });
    input.addEventListener('input', () => {
      if (touched) validateField(input);
    });
  });

  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', (event) => {
      const inputs = form.querySelectorAll('input[data-rules]');
      let formValid = true;
      inputs.forEach((input) => {
        if (!validateField(input)) formValid = false;
      });
      if (!formValid) event.preventDefault();
    });
  });
})();
