document.addEventListener('DOMContentLoaded', () => {
    const sourceList = document.getElementById('source-list');
    const sourceCount = document.getElementById('source-count');
    const chatContainer = document.getElementById('chat-container');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');

    // Load Sources
    fetch('/api/sources')
        .then(response => response.json())
        .then(data => {
            sourceCount.textContent = `${data.files.length} source(s)`;
            data.files.forEach(file => {
                const div = document.createElement('div');
                div.className = 'source-item';
                div.innerHTML = `
                    <span class="material-icons source-icon">picture_as_pdf</span>
                    <span class="source-name">${file}</span>
                `;
                div.onclick = () => window.open(`/manuals/${file}`, '_blank');
                sourceList.appendChild(div);
            });
        })
        .catch(err => console.error('Error loading sources:', err));

    // Handle sending messages
    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        // Clear input
        userInput.value = '';

        // Remove welcome message if it exists
        const welcome = document.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        // Add user message
        appendMessage('user', text);

        // Show loading state (simple for now)
        const loadingId = appendMessage('bot', '<span class="loading-dots">Thinking...</span>');

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: text })
            });
            const data = await response.json();

            // Remove loading message
            removeMessage(loadingId);

            // Add bot response
            appendMessage('bot', data.answer, data.sources);

        } catch (err) {
            console.error('Error sending message:', err);
            removeMessage(loadingId);
            appendMessage('bot', 'Sorry, something went wrong. Please try again.');
        }
    }

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    let msgIdCounter = 0;

    function appendMessage(role, text, sources = []) {
        const id = `msg-${msgIdCounter++}`;
        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.id = id;

        let contentHtml = `<div class="text">${formatText(text)}</div>`;

        if (sources && sources.length > 0) {
            contentHtml += `
                <div class="citations">
                    <div class="citation-title">Sources</div>
                    <div class="citation-list">
                        ${sources.map(s => `
                            <div class="citation-chip" title="${s.content.substring(0, 100)}...">
                                ${s.source} (p. ${s.page})
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        div.innerHTML = `
            <div class="message-content">
                ${contentHtml}
            </div>
        `;

        chatContainer.appendChild(div);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return id;
    }

    function removeMessage(id) {
        const msg = document.getElementById(id);
        if (msg) msg.remove();
    }

    function formatText(text) {
        // Simple formatter for newlines and bold
        return text
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    }
});
