import QtQuick
import QtQuick.Controls
import ".."
import "../components"

// Adds money to a goal, takes it back, or deletes the goal (`mode`).
Sheet {
    id: root
    property var goal: null
    property string mode: "deposit"

    readonly property bool deleting: mode === "delete"

    title: !goal ? ""
        : mode === "deposit" ? qsTr("Add to %1").arg(goal.name)
        : mode === "withdraw" ? qsTr("Take from %1").arg(goal.name)
        : qsTr("Delete %1?").arg(goal.name)
    subtitle: !goal ? ""
        : deleting
            ? (goal.hasMoney
               ? qsTr("The %1 saved in it goes back to the account you choose.").arg(goal.savedText)
               : qsTr("This goal holds no money. Deleting it cannot be undone."))
            : qsTr("%1 saved of %2").arg(goal.savedText).arg(goal.targetText)

    function openFor(item, action) {
        goal = item
        mode = action
        amount.text = ""
        savings.clearMessage()
        if (accounts.checkingOptions.length === 1) account.select(accounts.checkingOptions[0].key)
        else account.select(-1)
        open()
        if (!deleting) amount.input.forceActiveFocus()
    }

    function submit() {
        var key = account.currentKey === undefined ? -1 : account.currentKey
        if (deleting) savings.deleteGoal(goal.id, goal.uid, key)
        else savings.move(goal.id, goal.uid, amount.text, key, mode === "deposit")
    }

    Connections {
        target: savings
        function onSaved() { if (root.visible) root.close() }
    }

    Field {
        id: amount
        visible: !root.deleting
        width: parent.width
        label: qsTr("Amount (₺)")
        placeholder: "0,00"
        money: true
        onAccepted: root.submit()
    }

    Choice {
        id: account
        visible: !root.deleting || (root.goal !== null && root.goal.hasMoney)
        width: parent.width
        label: root.mode === "deposit" ? qsTr("Take from") : qsTr("Return to")
        placeholder: qsTr("Choose an account")
        model: accounts.checkingOptions
    }

    Notice {
        width: parent.width
        text: savings.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            quiet: root.deleting
            danger: root.deleting
            text: savings.busy ? qsTr("Working…")
                : root.mode === "deposit" ? qsTr("Add") : root.mode === "withdraw" ? qsTr("Take back") : qsTr("Delete goal")
            enabled: !savings.busy
            onClicked: root.submit()
        }
    ]
}
