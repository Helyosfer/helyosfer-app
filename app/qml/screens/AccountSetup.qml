import QtQuick
import QtQuick.Controls
import ".."
import "../components"

AuthFrame {
    title: "Add your first account"
    subtitle: "Start with the account you use most. You can add cards and other accounts later."

    function submit() { auth.createFirstAccount(name.text, balance.text) }

    Connections {
        target: auth
        function onRejected() { notice.nudge() }
    }

    Field {
        id: name
        width: parent.width
        label: "Account name"
        placeholder: "Main account"
        onAccepted: balance.input.forceActiveFocus()
        Component.onCompleted: input.forceActiveFocus()
    }

    Field {
        id: balance
        width: parent.width
        label: "Current balance (₺)"
        placeholder: "0,00"
        money: true
        input.inputMethodHints: Qt.ImhFormattedNumbersOnly
        onAccepted: submit()
    }

    Notice {
        id: notice
        width: parent.width
        text: auth.message
    }

    PrimaryButton {
        width: parent.width
        text: "Open Helysofer"
        enabled: name.text.trim().length > 0
        onClicked: submit()
    }
}
