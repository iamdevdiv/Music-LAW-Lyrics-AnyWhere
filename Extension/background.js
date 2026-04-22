chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
	if (changeInfo.status === 'complete' && tab.url.includes('music.youtube.com')) {
		chrome.scripting.executeScript({
			target: { tabId: tabId },
			function: initWebSocket,
			world: 'MAIN'
		});
	}
});

chrome.runtime.onInstalled.addListener((details) => {
	if (details.reason === chrome.runtime.OnInstalledReason.INSTALL) {
		chrome.tabs.create({
			url: "https://github.com/iamdevdiv/Music-LAW-Lyrics-AnyWhere"
		});
	}
});


function initWebSocket() {
	if (window.socket) {
		return;
	}

	window.socket = new WebSocket('ws://127.0.0.1:8765');

	window.socket.onclose = () => {
		socket = null;
		setTimeout(() => {
			initWebSocket();
		}, 5000);
	};

	window.socket.onerror = () => {
		window.socket.close();
	};

	window.sendSongDetails = () => {
		const minutesToSeconds = (timeStr) => {
			if (!timeStr) {
				return 0;
			}
			
			const parts = timeStr.split(":").map(part => parseInt(part.trim()));
			if (parts.length === 2) {
				return parts[0] * 60 + parts[1];
			} else if (parts.length === 3) {
				return parts[0] * 3600 + parts[1] * 60 + parts[2];
			}
			return 0;
		};
		
		const player = document.getElementById("movie_player");
		if (!player) {
			return;
		}

		const videoData = player.getVideoData();
		const { title, author } = videoData;

		const totalDuration = minutesToSeconds(document.querySelector(".time-info").textContent.replaceAll("\n", "").trim().split("/")[1]?.trim());
		if (totalDuration == 0) {
			return;
		}

		const currentDuration = Math.round(player.getCurrentTime());

		if (window.socket && window.socket.readyState === WebSocket.OPEN) {
			window.socket.send(JSON.stringify({
				songName: title,
				songArtists: author,
				totalDuration: parseInt(totalDuration),
				currentDuration: currentDuration
			}));
		}
	};

	if (!window.startedInterval) {
		window.startedInterval = true;

		setInterval(window.sendSongDetails, 100);
	}
}
