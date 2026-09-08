// Separate-origin outer proxy. The inner app gets an opaque sandbox origin.
(() => {
  if (window.parent === window || !document.referrer) throw new Error('Sandbox requires a parent');
  const parentOrigin = new URL(document.referrer).origin;
  const loopback = new Set(['127.0.0.1', 'localhost']);
  const parentURL = new URL(parentOrigin);
  if (parentOrigin === location.origin || parentURL.port !== location.port ||
      !loopback.has(parentURL.hostname) || !loopback.has(location.hostname)) throw new Error('Invalid parent origin');
  const inner = document.createElement('iframe');
  inner.setAttribute('sandbox', 'allow-scripts');
  inner.style.cssText = 'width:100%;height:100%;border:0';
  document.body.appendChild(inner);
  window.addEventListener('message', event => {
    const data = event.data;
    if (!data || data.jsonrpc !== '2.0') return;
    if (event.source === window.parent && event.origin === parentOrigin) {
      if (data.method === 'ui/notifications/sandbox-resource-ready') {
        if (typeof data.params?.html === 'string') inner.srcdoc = data.params.html;
      } else inner.contentWindow.postMessage(data, '*');
    } else if (event.source === inner.contentWindow && event.origin === 'null') {
      if (String(data.method || '').startsWith('ui/notifications/sandbox-')) return;
      window.parent.postMessage(data, parentOrigin);
    }
  });
  window.parent.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/sandbox-proxy-ready', params: {} }, parentOrigin);
})();
