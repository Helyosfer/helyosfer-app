import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    property var card: null

    title: card ? qsTr("Delete %1?").arg(card.name) : ""
    subtitle: qsTr("The card, its transactions and its installment plans are removed. This cannot be undone.")

    function openFor(account) {
        card = account
        accounts.clearMessage()
        open()
    }

    Connections {
        target: accounts
        function onSaved() { if (root.visible) root.close() }
    }

    Notice {
        width: parent.width
        text: accounts.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            quiet: true
            danger: true
            text: accounts.busy ? qsTr("Deleting…") : qsTr("Delete card")
            enabled: !accounts.busy
            onClicked: accounts.deleteCard(root.card.id)
        }
    ]
}
