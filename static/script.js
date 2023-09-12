let selectedConvElem = null;  // Global variable to track selected conversation

function appendConversationsToSidebar(data) {
    const sidebar = document.getElementById("sidebar");
    let currentGroup = null;

    data.forEach((conv) => {
        // Check if the conversation belongs to a new group
        if (conv.group !== currentGroup) {
            currentGroup = conv.group;

            // Add a group title to the sidebar
            sidebar.insertAdjacentHTML("beforeend", `
                <div class="p-2 text-gray-700 font-bold">
                    ${currentGroup || "No Group"}
                </div>
            `);
        }

        const convTitle = conv.title || "Untitled";
        sidebar.insertAdjacentHTML("beforeend", `
            <div class="p-2 hover:bg-gray-300 cursor-pointer flex justify-between" id="conv-${conv.id}">
                <span class="mr-2">${convTitle}</span>
                <small class="text-gray-500 whitespace-nowrap">${conv.created}</small>
            </div>
        `);

        // Add click event listener
        const convDiv = document.getElementById(`conv-${conv.id}`);
        convDiv.addEventListener("click", function () {
            loadMessages(conv.id);

            if (selectedConvElem) {
                selectedConvElem.classList.remove("bg-gray-400");
            }
            this.classList.add("bg-gray-400");
            selectedConvElem = this;
        });
    });
}

async function loadMessages(convId) {
    try {
        const response = await fetch(`/api/conversations/${encodeURIComponent(convId)}/messages`);
        const data = await response.json();

        const mainContent = document.getElementById("main-content");
        mainContent.innerHTML = ""; // Clear previous messages

        // Create a header with a link to the conversation
        mainContent.insertAdjacentHTML('beforeend', `
            <div class="p-2 border-b text-right">
                <a href="https://chat.openai.com/c/${data.conversation_id}"
                target="_blank" rel="noopener noreferrer" class="hover:underline">Open in ChatGPT ↗️</a>
            </div>
        `);

        // Populate the main content with messages
        const messages = data.messages;
        messages.forEach((msg) => {
            mainContent.insertAdjacentHTML('beforeend', `
                <div class="p-2 border-b">
                    <small class="text-gray-500">${msg.created}</small>
                    <br/>
                    <strong>${msg.role}:</strong>
                    <span>${msg.text}</span>
                </div>
            `);
        });

        // Scroll to the top of the main content area
        const mainContentWrapper = document.getElementById("main-content-wrapper");
        mainContentWrapper.scrollTop = 0;
    } catch (error) {
        console.error("Failed to load messages:", error);
    }
}

async function handleSearchInput(event) {
    if (event.key !== "Enter")
        return;

    const query = encodeURIComponent(searchInput.value);

    try {
        const response = await fetch(`/api/search?query=${query}`);
        const data = await response.json();

        const mainContent = document.getElementById("main-content");
        mainContent.innerHTML = ""; // Clear previous messages

        data.forEach((msg) => {
            mainContent.insertAdjacentHTML('beforeend', `
                <div class="p-2 border-b">
                    <strong>${msg.role}:</strong>
                    <span>${msg.text}</span>
                    <small class="text-gray-500">${msg.created}</small>
                </div>
            `);
        });
    } catch (error) {
        console.error("Search failed:", error);
    }
}

// Listen for Enter key press on searchInput element
const searchInput = document.getElementById("search-input");
searchInput.addEventListener("keydown", handleSearchInput);

async function loadConversations() {
    try {
        const response = await fetch("/api/conversations");
        const data = await response.json();

        const sidebar = document.getElementById("sidebar");
        sidebar.innerHTML = ""; // Clear previous conversations
        appendConversationsToSidebar(data);
    } catch (error) {
        console.error("Failed to load conversations:", error);
    }
}

async function loadActivityGraph() {
    try {
        const response = await fetch("/api/activity");
        const data = await response.json();
        buildActivityGraph(document.getElementById("activity-graph"), { data: data });
    } catch (error) {
        console.error("Failed to load activity graph:", error);
    }
}

window.addEventListener('DOMContentLoaded', (event) => {
    loadConversations();
    loadActivityGraph();
});
