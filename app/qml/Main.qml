import QtQuick
import QtQuick.Controls
import "."
import "screens"

ApplicationWindow {
    id: window
    width: 1280
    height: 800
    minimumWidth: 960
    minimumHeight: 620
    visible: true
    title: "Helyosfer"
    color: Theme.page

    // Where the main screen was, so that it comes back there when it is rebuilt.
    property string resumeSection: "overview"

    Binding { target: Theme; property: "dark"; value: app.dark }

    // Screens are created on demand, so an unopened screen costs no memory.
    Loader {
        id: screens
        anchors.fill: parent
        sourceComponent: {
            switch (app.screen) {
            case "setup": return setupScreen
            case "renewal": return setupScreen
            case "login": return loginScreen
            case "account_setup": return accountScreen
            case "home": return shellScreen
            case "failure": return failureScreen
            default: return null
            }
        }
    }

    // Text is looked up when a screen is created, so a new language means
    // creating the screen again.
    Connections {
        target: app
        function onLanguageChanged() {
            screens.active = false
            screens.active = true
        }
    }

    Component { id: setupScreen; Setup { renewal: app.screen === "renewal" } }
    Component { id: loginScreen; Login {} }
    Component { id: accountScreen; AccountSetup {} }
    Component { id: shellScreen; Shell {} }
    Component { id: failureScreen; Failure {} }
}
