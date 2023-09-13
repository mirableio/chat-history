let conversationData = null;

async function loadConversations() {
    try {
        const response = await fetch("/api/conversations");
        conversationData = await response.json();
        
        populateGroupDropdown(conversationData);
        populateConversationsList();
    } catch (error) {
        console.error("Failed to load conversations:", error);
    }
}

function populateGroupDropdown(conversations) {
    const groupSet = new Set();
    conversations.forEach(conv => {
        if (conv.group) {
            groupSet.add(conv.group);
        }
    });

    const groupFilterElem = document.getElementById("groupFilter");
    Array.from(groupSet).forEach(group => {
        const optionElem = document.createElement("option");
        optionElem.value = group;
        optionElem.textContent = group;
        groupFilterElem.appendChild(optionElem);
    });
}

let selectedConvElem = null;  // Global variable to track selected conversation

function populateConversationsList() {
    const sidebar = document.getElementById("sidebar-conversations");
    sidebar.innerHTML = ""; // Clear previous conversations

    const selectedGroup = document.getElementById("groupFilter").value;
    const searchText = document.getElementById("textFilter").value.toLowerCase();
    
    // Apply filters
    const filteredData = conversationData.filter(conv => {
        return (!selectedGroup || (conv.group && conv.group === selectedGroup) ||
                (selectedGroup == "*" && conv.is_favorite)) &&
                (!searchText || (conv.title && conv.title.toLowerCase().includes(searchText)));
    });

    let currentGroup = null;

    filteredData.forEach((conv) => {
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
    
        sidebar.insertAdjacentHTML("beforeend", `
            <div class="p-2 hover:bg-gray-300 cursor-pointer flex justify-between relative group" id="conv-${conv.id}">
                <span class="mr-2">${conv.title}</span>                
                <small class="text-gray-500 whitespace-nowrap" title="${conv.created.split(' ')[1]}">${conv.created.split(' ')[0]}</small>
        
                <div class="absolute right-20 top-0 pt-1 pr-1 group-hover:opacity-100 cursor-pointer heart-div ${conv.is_favorite ? "is-favorite" : ""}" onclick="handleHeartClick('${conv.id}')">
                    <span class="material-symbols-outlined heart-icon" style="font-variation-settings: 'opsz' 48; vertical-align: middle; font-size: 24px !important;">favorite</span>
                </div>
            </div>
        `);
    
        document.getElementById(`conv-${conv.id}`).addEventListener("click", function () {
            loadChatMessages(conv.id);

            unSelectConversation();
            this.classList.add("bg-gray-400");
            selectedConvElem = this;
        });
    });
}

async function handleHeartClick(convId) {
    try {
        const response = await fetch(`/api/toggle_favorite?conv_id=${convId}`, {
            method: "POST",
        });
        const data = await response.json();

        // Update the conversationData array
        const conversation = conversationData.find(conv => conv.id === convId);
        if (conversation) {
            conversation.is_favorite = data.is_favorite;
        }
        
        // Update the UI based on the new favorite status
        const heartContainer = document.querySelector(`#conv-${convId} .heart-div`);
        if (data.is_favorite) {
            heartContainer.classList.add("is-favorite");
        } else {
            heartContainer.classList.remove("is-favorite");
        }
    } catch (error) {
        console.error("Failed to toggle favorite status:", error);
    }
}

async function loadChatMessages(convId) {
    try {
        const response = await fetch(`/api/conversations/${encodeURIComponent(convId)}/messages`);
        const data = await response.json();

        const mainContent = document.getElementById("main-content");
        mainContent.innerHTML = ""; // Clear previous messages

        // Create a header with a link to the conversation
        mainContent.insertAdjacentHTML("beforeend", `
            <div class="p-2 border-b text-right">
                <a href="https://chat.openai.com/c/${data.conversation_id}"
                target="_blank" rel="noopener noreferrer" class="hover:underline">Open in ChatGPT 
                    <span class="material-symbols-outlined" style="font-variation-settings: 'opsz' 48; vertical-align: sub; font-size: 18px !important">open_in_new</span>
                </a>
            </div>
        `);

        // Populate the main content with messages
        const messages = data.messages;
        messages.forEach((msg, index) => {
            const bgColorClass = index % 2 === 0 ? '' : 'bg-gray-200';
            mainContent.insertAdjacentHTML('beforeend', `
                <div class="p-2 border-b ${bgColorClass}">
                    <small class="text-gray-500">${msg.created}</small>
                    <br/>
                    <strong>${msg.role}:</strong>
                    <span>${msg.text}</span>
                </div>
            `);
        });

        scrollToTop();
    } catch (error) {
        console.error("Failed to load messages:", error);
    }
}

async function loadActivityStats() {
    try {
        const response = await fetch("/api/activity");
        const data = await response.json();
        buildActivityGraph(document.getElementById("activity-graph"), { data: data });
        buildActivityBarChart(data);
    } catch (error) {
        console.error("Failed to load activity graph:", error);
    }
}

async function loadChatStatistics() {
    try {
        const response = await fetch('/api/statistics');
        const data = await response.json();
        const tableContainer = document.getElementById('chat-statistics');

        // Create table header and rows
        let tableHTML = `
            <table class="min-w-full bg-white">
                <tbody>
        `;

        // Insert table rows based on fetched data
        for (const [key, value] of Object.entries(data)) {
            tableHTML += `
                <tr>
                    <td class="py-2 px-4 border-b">${key}</td>
                    <td class="py-2 px-4 border-b">${value}</td>
                </tr>
            `;
        }

        // Close table tags
        tableHTML += `
                </tbody>
            </table>
        `;
    
        tableContainer.insertAdjacentHTML("beforeend", tableHTML);
    } catch (error) {
        console.error("Error fetching chat statistics:", error);
    }
}

async function searchConversations(query) { 
    try { 
        const mainContent = document.getElementById("main-content");
        
        mainContent.innerHTML = `
            <div class="p-2 pt-8">
                Searching...
                <span class="material-symbols-outlined" 
                    style="font-variation-settings: 'opsz' 48; 
                    vertical-align: sub; font-size: 18px !important">hourglass_top</span>
            </div>
        `;

        const response = await fetch(`/api/search?query=${query}`);
        const data = await response.json();

        mainContent.innerHTML = ""; // Clear previous messages

        if (data.length === 0) {
            // if msg is empty, display a message
            mainContent.insertAdjacentHTML('beforeend', `
                <div class="p-2 pt-8">
                    No results found.
                </div>
            `);
        }
        else{
            data.forEach((msg, index) => {
                const bgColorClass = index % 2 === 0 ? '' : 'bg-gray-200';
                mainContent.insertAdjacentHTML('beforeend', `
                    <div class="p-2 border-b pb-12 ${bgColorClass}">
                        <div><a href="https://chat.openai.com/c/${msg.id}"
                        target="_blank" rel="noopener noreferrer" class="hover:underline">${msg.title}
                        <span class="material-symbols-outlined" style="font-variation-settings: 'opsz' 48; vertical-align: middle; font-size: 18px !important">open_in_new</span>
                        </a></div>
                        <strong>${msg.role}:</strong>
                        <span>${msg.text}</span>
                        <small class="text-gray-500">${msg.created}</small>
                    </div>
                `);
            });
        }

        scrollToTop();
        unSelectConversation();
    } catch (error) {
        console.error("Search failed:", error);
    }
}

// Scroll to the top of the main content area
function scrollToTop() {
    document.getElementById("main-content-wrapper").scrollTop = 0;
}

// Remove background color from previously selected conversation
function unSelectConversation() {
    if (selectedConvElem) {
        selectedConvElem.classList.remove("bg-gray-400");
    }
}

// Listen for Enter key press on searchInput element
function handleSearchInput(event) {
    if (event.key !== "Enter")
        return;

    const query = encodeURIComponent(document.getElementById("search-input").value);
    if (query)
        searchConversations(query);
}

window.addEventListener('DOMContentLoaded', (event) => {
    loadConversations();
    loadActivityStats();
    loadChatStatistics();

    document.getElementById("search-input").addEventListener("keydown", handleSearchInput);
    document.getElementById("groupFilter").addEventListener("change", populateConversationsList);
    document.getElementById("textFilter").addEventListener("input", populateConversationsList);
});
