import QtQuick
import QtQuick.Controls
import ".."
import "../components"
import "../dialogs"

// Signed-in frame: navigation rail on the left, the selected section on the right.
Rectangle {
    id: root
    objectName: "shell"
    property string section: "overview"
    readonly property bool dialogOpen: addTransaction.visible || addAccount.visible
        || payDebt.visible || confirmDelete.visible || addDebt.visible
        || payInstallments.visible || addRecurring.visible || stopRecurring.visible
        || autoPayDay.visible || reschedule.visible || changeAmount.visible
        || addAsset.visible || sellAsset.visible || addGoal.visible || moveSavings.visible
        || addPlanItem.visible
    color: Theme.page

    property string pendingTool: ""

    // Goes to a section; "calendar" opens the calendar tool on a given date.
    function open(target, argument) {
        search.clear()
        if (target === "calendar") {
            calendar.showDate(argument)
            pendingTool = "calendar"
            section = "tools"
        } else {
            section = target
        }
    }

    readonly property var sections: [
        { key: "overview", label: "Overview", glyph: "" },
        { key: "assets", label: "Assets", glyph: "" },
        { key: "cards", label: "Cards and accounts", glyph: "" },
        { key: "debts", label: "Debts and payments", glyph: "" },
        { key: "subscriptions", label: "Subscriptions", glyph: "" },
        { key: "savings", label: "Savings goals", glyph: "" },
        { key: "tools", label: "Tools", glyph: "" },
        { key: "settings", label: "Settings", glyph: "" }
    ]

    Rectangle {
        id: rail
        width: 216
        height: parent.height
        color: Theme.page

        Rectangle {
            anchors.right: parent.right
            width: 1
            height: parent.height
            color: Theme.lineSoft
        }

        Column {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 2

            Row {
                height: 44
                leftPadding: 8
                spacing: 10

                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 22; height: 22; radius: 6
                    color: Theme.accent
                    Text {
                        anchors.centerIn: parent
                        text: "H"
                        color: Theme.onAccent
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                    }
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Helysofer"
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                }
            }

            Item { width: 1; height: 8 }

            Repeater {
                model: root.sections
                NavItem {
                    required property var modelData
                    width: rail.width - 24
                    text: modelData.label
                    glyph: modelData.glyph
                    selected: root.section === modelData.key
                    onClicked: root.section = modelData.key
                }
            }
        }

        Column {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 12
            spacing: 2

            NavItem {
                width: parent.width
                text: Theme.dark ? "Light theme" : "Dark theme"
                glyph: ""
                onClicked: app.toggleTheme()
            }
            NavItem {
                width: parent.width
                text: "Lock"
                glyph: ""
                onClicked: auth.logout()
            }
            Text {
                leftPadding: 10
                topPadding: 8
                text: "Encrypted on this device  ·  " + app.version
                color: Theme.faint
                font.family: Theme.uiFont
                font.pixelSize: 11
            }
        }
    }

    Loader {
        anchors.left: rail.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        sourceComponent: root.section === "overview" ? overview
            : root.section === "cards" ? cards
            : root.section === "debts" ? debtsSection
            : root.section === "subscriptions" ? subscriptionsSection
            : root.section === "settings" ? settingsSection
            : root.section === "assets" ? assetsSection
            : root.section === "savings" ? savingsSection
            : root.section === "tools" ? toolsSection : pending
    }

    Component {
        id: overview
        Dashboard {
            onAddRequested: addTransaction.openFor(-1)
            onEditRequested: function (transactionId) { addTransaction.openForEdit(transactionId) }
            onOpenRequested: function (section, argument) { root.open(section, argument) }
        }
    }

    Component {
        id: cards
        Accounts {
            onAddAccountRequested: addAccount.openFresh()
            onAddTransactionRequested: function (accountId) { addTransaction.openFor(accountId) }
            onPayDebtRequested: function (account) { payDebt.openFor(account) }
            onDeleteRequested: function (account) { confirmDelete.openFor(account) }
        }
    }

    Component {
        id: debtsSection
        Debts {
            onAddRequested: addDebt.openFresh()
            onPayRequested: function (debt, payOff) { payInstallments.openFor(debt, payOff) }
            onAutoPayRequested: function (debt) { autoPayDay.openFor(debt, "1") }
            onRescheduleRequested: function (item) { reschedule.openFor(item, "") }
        }
    }

    Component {
        id: subscriptionsSection
        Subscriptions {
            onAddRequested: addRecurring.openFresh()
            onAmountRequested: function (item) { changeAmount.openFor(item, "") }
            onStopRequested: function (item) { stopRecurring.openFor(item) }
        }
    }

    Component { id: settingsSection; Settings {} }

    Component {
        id: assetsSection
        Assets {
            onAddRequested: addAsset.openFresh()
            onSellRequested: function (holding) { sellAsset.openFor(holding) }
        }
    }

    Component {
        id: savingsSection
        Savings {
            onAddRequested: addGoal.openFresh()
            onMoveRequested: function (goal, mode) { moveSavings.openFor(goal, mode) }
        }
    }

    Component {
        id: toolsSection
        Tools {
            objectName: "tools"
            Component.onCompleted: {
                if (root.pendingTool.length > 0) { tool = root.pendingTool; root.pendingTool = "" }
            }
            onAddPlanItemRequested: addPlanItem.openFresh()
            onEditPlanItemRequested: function (item) { addPlanItem.openFor(item) }
            onEditTransactionRequested: function (transactionId) { addTransaction.openForEdit(transactionId) }
        }
    }

    AddPlanItem { id: addPlanItem; objectName: "addPlanItem" }

    AddGoal { id: addGoal; objectName: "addGoal" }
    MoveSavings { id: moveSavings; objectName: "moveSavings" }
    AddAsset { id: addAsset; objectName: "addAsset" }
    SellAsset { id: sellAsset; objectName: "sellAsset" }

    AddDebt { id: addDebt; objectName: "addDebt" }
    PayInstallments { id: payInstallments; objectName: "payInstallments" }
    AddRecurring { id: addRecurring; objectName: "addRecurring" }
    StopRecurring { id: stopRecurring; objectName: "stopRecurring" }
    Prompt {
        id: autoPayDay
        objectName: "autoPayDay"
        source: debts
        title: "Pay automatically"
        subtitle: subject ? subject.monthlyText + " is taken for " + subject.name + " each month." : ""
        fieldLabel: "Day of the month (1–31)"
        confirmText: "Turn on"
        onSubmitted: function (text) { debts.setAutoPay(subject.id, true, text) }
    }
    Prompt {
        id: reschedule
        objectName: "reschedule"
        source: debts
        title: "Reschedule"
        subtitle: subject ? subject.title + "  ·  " + subject.amount : ""
        fieldLabel: "New date"
        fieldPlaceholder: "DD.MM.YYYY"
        onSubmitted: function (text) { debts.reschedule(subject.id, text) }
    }
    Prompt {
        id: changeAmount
        objectName: "changeAmount"
        source: recurring
        title: "Change amount"
        subtitle: subject ? subject.name + "  ·  currently " + subject.amountText : ""
        fieldLabel: "New amount (₺)"
        money: true
        fieldPlaceholder: "0,00"
        onSubmitted: function (text) { recurring.changeAmount(subject.id, text) }
    }

    AddTransaction { id: addTransaction; objectName: "addTransaction" }
    AddAccount { id: addAccount; objectName: "addAccount" }
    PayDebt { id: payDebt; objectName: "payDebt" }
    ConfirmDelete { id: confirmDelete; objectName: "confirmDelete" }

    Shortcut {
        sequence: "Ctrl+N"
        enabled: !root.dialogOpen
        onActivated: addTransaction.openFor(-1)
    }

    Component {
        id: pending
        Item {
            Column {
                anchors.centerIn: parent
                spacing: 8
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: {
                        for (var i = 0; i < root.sections.length; i++)
                            if (root.sections[i].key === root.section) return root.sections[i].label
                        return ""
                    }
                    color: Theme.text
                    font.family: Theme.displayFont
                    font.pixelSize: 22
                    font.weight: Font.Light
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "This section is being built."
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }
            }
        }
    }
}
