let selectedConvElem = null;  // Global variable to track selected conversation

function appendConversationsToSidebar(data) {
    const sidebar = document.getElementById('sidebar');
    data.forEach(conv => {
        const convDiv = document.createElement('div');
        convDiv.className = 'p-2 hover:bg-gray-300 cursor-pointer';
        const convTitle = conv.title || 'Untitled';
        convDiv.innerHTML = `<span>${convTitle}</span>
            <small class="text-gray-500">${conv.created}</small>
        `;
        // convDiv.addEventListener('click', () => loadMessages(conv.id));
        convDiv.addEventListener('click', function() {
            loadMessages(conv.id);

            // Remove the highlight class from the previously selected conversation
            if (selectedConvElem) {
                selectedConvElem.classList.remove('bg-gray-400');
            }

            // Add the highlight class to the currently selected conversation
            this.classList.add('bg-gray-400');

            // Update the selected conversation element
            selectedConvElem = this;
        });
        sidebar.appendChild(convDiv);
    });
}

function loadMessages(convId) {
    fetch(`/api/conversations/${convId}/messages`)
        .then(response => response.json())
        .then(data => {
            const mainContent = document.getElementById('main-content');
            mainContent.innerHTML = '';  // Clear previous messages
            const headerDiv = document.createElement('div');
            headerDiv.className = 'p-2 border-b';
            headerDiv.innerHTML = `
                <a href="https://chat.openai.com/c/${data.conversation_id}" 
                target="_blank">Open in ChatGPT</a>
            `;
            mainContent.appendChild(headerDiv);

            const messages = data.messages;
            messages.forEach(msg => {
                const msgDiv = document.createElement('div');
                msgDiv.className = 'p-2 border-b';
                msgDiv.innerHTML = `
                    <small class="text-gray-500">${msg.created}</small>
                    <br/>
                    <strong>${msg.role}:</strong>
                    <span>${msg.text}</span>
                `;
                mainContent.appendChild(msgDiv);
            });

            // Scroll to the top of the main content area
            const mainContentWrapper = document.getElementById('main-content-wrapper');
            mainContentWrapper.scrollTop = 0;
        });
}

function showTooltip(convDiv, conv) {
    // Logic to show tooltip with created date and duration
}

function handleSearchInput(event) {
    if (event.key !== "Enter")
        return;

    const query = searchInput.value;

    // Perform search based on the query
    fetch(`/api/search?query=${query}`)
        .then(response => response.json())
        .then(data => {
            const mainContent = document.getElementById('main-content');
            mainContent.innerHTML = '';  // Clear previous messages
            data.forEach(msg => {
                const msgDiv = document.createElement('div');
                msgDiv.className = 'p-2 border-b';
                msgDiv.innerHTML = `
                    <strong>${msg.role}:</strong>
                    <span>${msg.text}</span>
                    <small class="text-gray-500">${msg.created}</small>
                `;
                mainContent.appendChild(msgDiv);
            });
        });
}

function loadConversations() {
    fetch('/api/conversations')
        .then(response => response.json())
        .then(data => {
            const sidebar = document.getElementById('sidebar');
            sidebar.innerHTML = '';  // Clear previous conversations
            appendConversationsToSidebar(data);
        });
}

const searchInput = document.getElementById('search-input');
searchInput.addEventListener('keydown', handleSearchInput);

loadConversations();
