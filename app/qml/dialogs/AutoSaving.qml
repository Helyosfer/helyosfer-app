import QtQuick
import QtQuick.Controls
import ".."
import "../components"

// Sets, changes or turns off a goal's monthly contribution.
Sheet {
    id: root
    property var goal: null

    title: goal ? qsTr("Save for %1 automatically").arg(goal.name) : ""
    subtitle: qsTr("The amount moves from the account into the goal once a month, the next time you open Helyosfer on or after that day. A month the account cannot cover is skipped.")

    function openFor(item) {
        goal = item
        savings.clearMessage()
        amount.text = item.autoAmountText
        day.text = item.autoDay > 0 ? String(item.autoDay) : ""
        if (item.autoAccount >= 0) account.select(item.autoAccount)
        else if (accounts.checkingOptions.length === 1) account.select(accounts.checkingOptions[0].key)
        else account.select(-1)
        open()
        amount.input.forceActiveFocus()
    }

    function submit() {
        savings.setAuto(goal.uid, amount.text, day.text,
                        account.currentKey === undefined ? -1 : account.currentKey)
    }

    Connections {
        target: savings
        function onSaved() { if (root.visible) root.close() }
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: amount
            width: (parent.width - 12) * 0.6
            label: qsTr("Amount each month (₺)")
            placeholder: "0,00"
            money: true
            onAccepted: root.submit()
        }
        Field {
            id: day
            width: (parent.width - 12) * 0.4
            label: qsTr("Day of the month (1–31)")
            placeholder: "1"
            onAccepted: root.submit()
        }
    }

    Choice {
        id: account
        width: parent.width
        label: qsTr("Take from")
        placeholder: qsTr("Choose an account")
        model: accounts.checkingOptions
    }

    Notice {
        width: parent.width
        text: savings.message
    }

    footer: [
        PrimaryButton {
            quiet: true
            danger: true
            visible: root.goal !== null && root.goal.auto
            text: qsTr("Turn off")
            enabled: !savings.busy
            onClicked: savings.clearAuto(root.goal.uid)
        },
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            text: savings.busy ? qsTr("Saving…") : qsTr("Save")
            enabled: !savings.busy
            onClicked: root.submit()
        }
    ]
}
