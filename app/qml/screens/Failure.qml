import QtQuick
import ".."
import "../components"

// Shown instead of the application when startup had to stop. It depends on
// nothing but fixed text, so it can stand up even when the profile cannot.
AuthFrame {
    title: app.failureTitle
    subtitle: app.failureMessage

    Notice {
        width: parent.width
        problem: false
        text: "Nothing was changed. Close this window when you are ready."
    }

    PrimaryButton {
        text: "Close"
        onClicked: Qt.quit()
    }
}
