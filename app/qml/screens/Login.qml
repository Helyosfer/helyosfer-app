import QtQuick
import QtQuick.Controls
import ".."
import "../components"

AuthFrame {
    title: qsTr("Welcome back")
    subtitle: qsTr("Your records are encrypted on this device. Enter your password to open them.")

    function submit() {
        auth.login(password.text)
        password.text = ""
    }

    Connections {
        target: auth
        function onRejected() { notice.nudge(); password.input.forceActiveFocus() }
    }

    Field {
        id: password
        width: parent.width
        label: qsTr("Password")
        echoMode: TextInput.Password
        input.enabled: !auth.busy
        onAccepted: submit()
        Component.onCompleted: input.forceActiveFocus()
    }

    Notice {
        id: notice
        width: parent.width
        text: auth.message
    }

    PrimaryButton {
        width: parent.width
        text: auth.busy ? qsTr("Checking…") : qsTr("Unlock")
        enabled: !auth.busy && password.text.length > 0
        onClicked: submit()
    }
}
