import QtQuick
import QtQuick.Controls
import ".."
import "../components"

AuthFrame {
    property bool renewal: false

    title: renewal ? qsTr("Choose a new password") : qsTr("Create your password")
    subtitle: renewal
        ? qsTr("Your current password is older than today's rules. Set a stronger one to continue.")
        : qsTr("This password protects your records on this device. It is never sent anywhere, and it cannot be recovered if you forget it.")

    function submit() { auth.setup(password.text, confirmation.text) }

    Connections {
        target: auth
        function onRejected() { notice.nudge() }
    }

    Field {
        id: password
        width: parent.width
        label: qsTr("Password")
        echoMode: TextInput.Password
        input.enabled: !auth.busy
        onAccepted: confirmation.input.forceActiveFocus()
        Component.onCompleted: input.forceActiveFocus()
    }

    Field {
        id: confirmation
        width: parent.width
        label: qsTr("Repeat password")
        echoMode: TextInput.Password
        input.enabled: !auth.busy
        onAccepted: submit()
    }

    Notice {
        width: parent.width
        problem: false
        visible: auth.message.length === 0
        text: qsTr("At least 12 characters, with upper and lower case letters, a digit and a symbol.")
    }

    Notice {
        id: notice
        width: parent.width
        text: auth.message
    }

    PrimaryButton {
        width: parent.width
        text: auth.busy ? qsTr("Saving…") : qsTr("Continue")
        enabled: !auth.busy && password.text.length > 0 && confirmation.text.length > 0
        onClicked: submit()
    }
}
