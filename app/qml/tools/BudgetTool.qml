import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Column {
    id: root
    signal addRequested()
    signal editRequested(var item)
    spacing: Theme.gap

    Component.onCompleted: budget.refresh()

    Item {
        width: parent.width
        height: stepper.height

        MonthStepper {
            id: stepper
            title: budget.monthTitle
            onPrevious: budget.previous()
            onNext: budget.next()
        }
        Row {
            anchors.right: parent.right
            spacing: 8
            PrimaryButton {
                compact: true; quiet: true
                text: qsTr("Copy to the rest of the year")
                enabled: !budget.busy && budget.items.length > 0
                onClicked: budget.applyToYearEnd()
            }
            PrimaryButton {
                compact: true
                text: qsTr("Add plan item")
                onClicked: root.addRequested()
            }
        }
    }

    Notice {
        width: parent.width
        problem: budget.message.length > 0
        text: budget.message.length > 0 ? budget.message : budget.notice
    }

    // -- Summary ------------------------------------------------------------
    Card {
        width: parent.width

        Row {
            width: parent.width

            Repeater {
                model: [
                    { label: qsTr("Planned income"), value: budget.incomeText, tone: 0 },
                    { label: qsTr("Planned spending"), value: budget.expenseText, tone: 0 },
                    { label: qsTr("Reserved for recurring payments"), value: budget.reservedText, tone: 0 },
                    { label: qsTr("Left to plan"), value: budget.leftText, tone: budget.leftDirection }
                ]
                Column {
                    required property var modelData
                    width: parent.width / 4
                    spacing: 2
                    Text {
                        width: parent.width - 12
                        text: modelData.label
                        color: Theme.muted
                        font.family: Theme.uiFont
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    Counting {
                        value: modelData.value
                        place: "budget:" + modelData.label
                        color: modelData.tone < 0 ? Theme.down : modelData.tone > 0 ? Theme.up : Theme.text
                        font.family: Theme.displayFont
                        font.pixelSize: 22
                        font.weight: Font.Light
                    }
                }
            }
        }
    }

    // -- Spending against the plan -------------------------------------------
    Card {
        width: parent.width
        visible: budget.progress.length > 0

        Column {
            width: parent.width

            Text {
                bottomPadding: 10
                text: qsTr("Spending against the plan")
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }

            Repeater {
                model: budget.progress

                Item {
                    id: row
                    required property var modelData
                    width: parent.width
                    height: 54

                    Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                    Column {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 7

                        Item {
                            width: parent.width
                            height: label.height
                            Text {
                                id: label
                                text: row.modelData.category
                                color: Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 13
                            }
                            Text {
                                anchors.right: parent.right
                                text: qsTr("%1 of %2").arg(row.modelData.spentText).arg(row.modelData.plannedText)
                                    + "  ·  " + row.modelData.note
                                color: row.modelData.over ? Theme.down
                                    : row.modelData.near ? Theme.warn : Theme.muted
                                font.family: Theme.dataFont
                                font.pixelSize: 12
                            }
                        }
                        Rectangle {
                            width: parent.width
                            height: 6
                            radius: 3
                            color: Theme.lineSoft
                            Rectangle {
                                width: parent.width * row.modelData.ratio
                                Behavior on width { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutCubic } }
                                height: parent.height
                                radius: 3
                                color: row.modelData.over ? Theme.down
                                    : row.modelData.near ? Theme.warn : Theme.accent
                                Behavior on color { ColorAnimation { duration: Theme.slow } }
                            }
                        }
                    }
                }
            }
        }
    }

    // -- Plan items ---------------------------------------------------------
    Card {
        width: parent.width

        Column {
            width: parent.width

            Text {
                bottomPadding: 10
                text: qsTr("Plan items")
                color: Theme.text
                font.family: Theme.uiFont
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }

            Text {
                width: parent.width
                visible: budget.items.length === 0
                topPadding: 6
                text: qsTr("Nothing planned for this month. Add your expected income and the spending you want to cap.")
                color: Theme.faint
                font.family: Theme.uiFont
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: budget.items

                Item {
                    id: line
                    required property var modelData
                    width: parent.width
                    height: 44

                    Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.right: sum.left
                        anchors.rightMargin: 16
                        text: line.modelData.name
                            + (line.modelData.category.length > 0 ? "  ·  " + line.modelData.category : "")
                            + (line.modelData.everyMonth ? "  ·  " + qsTr("every month") : "")
                            + (line.modelData.rollover ? "  ·  " + qsTr("carries over") : "")
                        color: Theme.text
                        font.family: Theme.uiFont
                        font.pixelSize: 13
                        elide: Text.ElideRight
                    }
                    Text {
                        id: sum
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.right: rowActions.left
                        anchors.rightMargin: 20
                        text: (line.modelData.income ? "+" : "−") + line.modelData.amountText
                        color: line.modelData.income ? Theme.up : Theme.text
                        font.family: Theme.dataFont
                        font.pixelSize: 13
                    }
                    Row {
                        id: rowActions
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8
                        PrimaryButton {
                            compact: true; quiet: true
                            text: qsTr("Edit")
                            onClicked: root.editRequested(line.modelData)
                        }
                        PrimaryButton {
                            compact: true; quiet: true; danger: true
                            text: qsTr("Remove")
                            enabled: !budget.busy
                            onClicked: budget.deleteItem(line.modelData.id)
                        }
                    }
                }
            }
        }
    }
}
