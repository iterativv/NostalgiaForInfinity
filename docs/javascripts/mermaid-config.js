// Wait for document ready
document.addEventListener('DOMContentLoaded', function() {
  // Get theme from Material
  const getTheme = () => {
    const palette = document.body.getAttribute('data-md-color-scheme');
    return palette === 'slate' ? 'dark' : 'default';
  };

  // Initialize Mermaid
  mermaid.initialize({
    startOnLoad: true,
    theme: getTheme(),
    themeVariables: {
      darkMode: getTheme() === 'dark'
    }
  });

  // Re-render on theme change
  const observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
      if (mutation.attributeName === 'data-md-color-scheme') {
        location.reload();
      }
    });
  });

  observer.observe(document.body, {
    attributes: true,
    attributeFilter: ['data-md-color-scheme']
  });
});
