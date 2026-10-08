import QtQuick
import QtQuick.Controls
import ".."
import "../components"

AuthFrame {
    property bool renewal: false

    title: renewal ? "Choose a new password" : "Create your password"
    subtitle: renewal
        ? "Your current password is older than today's rules. Set a stronger one to continue."
        : "This password protects your records on this device. It is never sent anywhere, and it cannot be recovered if you forget it."

    function submit() { auth.setup(password.text, confirmation.text) }

    Connections {
        target: auth
        function onRejected() { notice.nudge() }
    }

    Field {
        id: password
        width: parent.width
        label: "Password"
        echoMode: TextInput.Password
        input.enabled: !auth.busy
        onAccepted: confirmation.input.forceActiveFocus()
        Component.onCompleted: input.forceActiveFocus()
    }

    Field {
        id: confirmation
        width: parent.width
        label: "Repeat password"
        echoMode: TextInput.Password
        input.enabled: !auth.busy
        onAccepted: submit()
    }

    Notice {
        width: parent.width
        problem: false
        visible: auth.message.length === 0
        text: "At least 12 characters, with upper and lower case letters, a digit and a symbol."
    }

    Notice {
        id: notice
        width: parent.width
        text: auth.message
    }

    PrimaryButton {
        width: parent.width
        text: auth.busy ? "Saving…" : "Continue"
        enabled: !auth.busy && password.text.length > 0 && confirmation.text.length > 0
        onClicked: submit()
    }
}
