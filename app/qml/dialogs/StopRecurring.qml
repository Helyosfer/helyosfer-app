import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    property var item: null
    property string charge: ""

    title: item ? qsTr("Stop %1?").arg(item.name) : ""
    subtitle: qsTr("It will no longer be charged or shown here. Past transactions stay as they are.")

    function openFor(payment) {
        item = payment
        charge = payment.income ? "" : recurring.chargeThisMonth(payment.id)
        refund.checked = false
        recurring.clearMessage()
        open()
    }

    Connections {
        target: recurring
        function onSaved() { if (root.visible) root.close() }
    }

    Toggle {
        id: refund
        visible: root.charge.length > 0
        text: qsTr("Add this month's %1 back to the account").arg(root.charge)
    }

    Notice {
        width: parent.width
        text: recurring.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            quiet: true
            danger: true
            text: recurring.busy ? qsTr("Stopping…") : qsTr("Stop")
            enabled: !recurring.busy
            onClicked: recurring.cancel(root.item.id, refund.visible && refund.checked)
        }
    ]
}
