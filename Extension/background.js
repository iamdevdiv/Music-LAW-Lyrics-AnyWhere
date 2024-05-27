chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete' && tab.url.includes('music.youtube.com')) {
        chrome.scripting.executeScript({
            target: { tabId: tabId },
            function: initWebSocket
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

    window.socket = new WebSocket('ws://localhost:8765');

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
        const songDetailsParent = document.querySelector(".content-info-wrapper.style-scope.ytmusic-player-bar");
        
        const songName = songDetailsParent.firstElementChild.innerHTML;
        const currentDuration = document.getElementById("progress-bar").querySelector(".slider-knob-inner.style-scope.tp-yt-paper-slider").getAttribute("value");

        const songDetails = songDetailsParent.querySelectorAll(".yt-simple-endpoint.style-scope.yt-formatted-string");
        let songArtistsAndAlbum = [];
        songDetails.forEach(elem => {
            songArtistsAndAlbum.push(elem.innerHTML)
        });

        if (window.socket && window.socket.readyState === WebSocket.OPEN) {
            window.socket.send(JSON.stringify({
                songName: songName,
                songArtistsAndAlbum: songArtistsAndAlbum.join(" "),
                currentDuration: currentDuration
            }));
        }
    };

    if (!window.observingChanges) {
        window.observingChanges = true;

        const observer = new MutationObserver(() => {
            window.sendSongDetails();
        });
        
        const config = { attributes: true };
        observer.observe(document.getElementById("progress-bar").querySelector(".slider-knob-inner.style-scope.tp-yt-paper-slider"), config);        
    }
}
