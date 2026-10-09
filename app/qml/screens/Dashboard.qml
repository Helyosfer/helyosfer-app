import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Flickable {
    id: root
    signal addRequested()
    signal editRequested(int transactionId)
    signal openRequested(string section, string argument)
    contentWidth: width
    contentHeight: page.implicitHeight + 48
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Component.onCompleted: dashboard.refresh()

    Column {
        id: page
        x: 28
        y: 24
        width: Math.min(root.width - 56, 1180)
        spacing: Theme.gap

        Item {
            width: parent.width
            height: addButton.height

            Field {
                id: searchBox
                objectName: "searchBox"
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(420, parent.width - addButton.width - 24)
                placeholder: "Search transactions, accounts and categories   Ctrl+K"
                onTextChanged: search.search(text)
                Keys.onEscapePressed: text = ""
            }
            Shortcut {
                sequence: "Ctrl+K"
                onActivated: searchBox.input.forceActiveFocus()
            }
            PrimaryButton {
                id: addButton
                anchors.right: parent.right
                text: "Add transaction"
                ToolTip.visible: hovered
                ToolTip.delay: 600
                ToolTip.text: "Ctrl+N"
                onClicked: root.addRequested()
            }
        }

        // -- Search results ------------------------------------------------
        Card {
            width: parent.width
            visible: search.active

            Column {
                width: parent.width

                Text {
                    visible: search.results.length === 0
                    text: search.searching ? "Searching…" : "Nothing matches."
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }

                Repeater {
                    model: search.results

                    AbstractButton {
                        id: hit
                        required property var modelData
                        required property int index
                        width: parent.width
                        height: 42
                        enabled: modelData.target.length > 0
                        hoverEnabled: true
                        Accessible.name: modelData.title
                        onClicked: root.openRequested(modelData.target, modelData.argument)

                        background: Rectangle {
                            color: hit.hovered && hit.enabled ? Theme.raised : "transparent"
                            radius: Theme.controlRadius
                            border.width: hit.visualFocus ? 2 : 0
                            border.color: Theme.accent
                            Rectangle {
                                visible: hit.index > 0
                                width: parent.width; height: 1; color: Theme.lineSoft
                            }
                        }
                        contentItem: Item {
                            Text {
                                id: hitKind
                                anchors.verticalCenter: parent.verticalCenter
                                width: 96
                                text: hit.modelData.kind
                                color: Theme.faint
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: hitKind.right
                                anchors.right: hitDetail.left
                                anchors.rightMargin: 16
                                text: hit.modelData.title
                                color: Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 13
                                elide: Text.ElideRight
                            }
                            Text {
                                id: hitDetail
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.right: parent.right
                                anchors.rightMargin: 4
                                text: hit.modelData.detail
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                        }
                    }
                }
            }
        }

        Text {
            width: parent.width
            visible: dashboard.error.length > 0
            text: dashboard.error
            color: Theme.down
            font.family: Theme.uiFont
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }

        // -- Balance stage -------------------------------------------------
        Card {
            width: parent.width

            Column {
                width: parent.width
                spacing: 14

                Item {
                    width: parent.width
                    height: headline.height

                    Column {
                        id: headline
                        spacing: 4

                        Text {
                            text: "Total balance"
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                        }
                        Row {
                            spacing: 2
                            Text {
                                id: whole
                                text: dashboard.balanceWhole
                                color: Theme.text
                                font.family: Theme.displayFont
                                font.pixelSize: 48
                                font.weight: Font.Light
                            }
                            Text {
                                anchors.baseline: whole.baseline
                                text: dashboard.balanceFraction
                                color: Theme.muted
                                font.family: Theme.displayFont
                                font.pixelSize: 22
                                font.weight: Font.Light
                            }
                        }
                        Text {
                            text: dashboard.changeText
                            color: Theme.direction(dashboard.changeDirection)
                            font.family: Theme.dataFont
                            font.pixelSize: 12
                        }
                    }

                    Segmented {
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        model: dashboard.periods
                        current: dashboard.period
                        onChosen: function (key) { dashboard.setPeriod(key) }
                    }
                }

                LineChart {
                    width: parent.width
                    height: 220
                    values: dashboard.series
                    labels: dashboard.seriesLabels
                }

                Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }

                Row {
                    width: parent.width

                    Repeater {
                        model: [
                            { label: "Income", value: dashboard.incomeText, tone: 0 },
                            { label: "Spending", value: dashboard.expenseText, tone: 0 },
                            { label: "Net", value: dashboard.netText, tone: dashboard.netDirection }
                        ]
                        Column {
                            required property var modelData
                            width: parent.width / 3
                            spacing: 2
                            Text {
                                text: modelData.label
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 12
                            }
                            Text {
                                text: modelData.value
                                color: modelData.tone === 0 ? Theme.text : Theme.direction(modelData.tone)
                                font.family: Theme.uiFont
                                font.pixelSize: 17
                                font.weight: Font.Medium
                            }
                        }
                    }
                }
            }
        }

        // -- Coming up -----------------------------------------------------
        Card {
            width: parent.width
            visible: dashboard.upcoming.length > 0

            Column {
                width: parent.width

                Text {
                    bottomPadding: 10
                    text: "Coming up"
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Repeater {
                    model: dashboard.upcoming

                    AbstractButton {
                        id: due
                        required property var modelData
                        width: parent.width
                        height: 46
                        hoverEnabled: true
                        Accessible.name: modelData.title + ", " + modelData.when
                        onClicked: root.openRequested(modelData.section, "")

                        background: Rectangle {
                            color: due.hovered ? Theme.raised : "transparent"
                            radius: Theme.controlRadius
                            border.width: due.visualFocus ? 2 : 0
                            border.color: Theme.accent
                            Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                        }
                        contentItem: Item {
                            Column {
                                id: dueDate
                                anchors.verticalCenter: parent.verticalCenter
                                width: 44
                                Text {
                                    text: due.modelData.day
                                    color: Theme.text
                                    font.family: Theme.dataFont
                                    font.pixelSize: 14
                                }
                                Text {
                                    text: due.modelData.month
                                    color: Theme.faint
                                    font.family: Theme.dataFont
                                    font.pixelSize: 10
                                }
                            }
                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: dueDate.right
                                anchors.right: dueAmount.left
                                anchors.rightMargin: 16
                                spacing: 1
                                Text {
                                    width: parent.width
                                    text: due.modelData.title
                                    color: Theme.text
                                    font.family: Theme.uiFont
                                    font.pixelSize: 13
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: due.modelData.when + "  ·  " + due.modelData.note
                                    color: due.modelData.overdue ? Theme.warn : Theme.muted
                                    font.family: Theme.uiFont
                                    font.pixelSize: 12
                                }
                            }
                            Text {
                                id: dueAmount
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.right: parent.right
                                anchors.rightMargin: 4
                                text: due.modelData.amount
                                color: due.modelData.income ? Theme.up : Theme.text
                                font.family: Theme.dataFont
                                font.pixelSize: 13
                            }
                        }
                    }
                }
            }
        }

        // -- Recent transactions -------------------------------------------
        Card {
            width: parent.width

            Column {
                width: parent.width
                spacing: 0

                Text {
                    bottomPadding: 10
                    text: "Recent transactions"
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Text {
                    visible: dashboard.recent.length === 0
                    topPadding: 6
                    text: "Transactions you add will appear here."
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }

                Repeater {
                    model: dashboard.recent

                    Item {
                        id: row
                        required property var modelData
                        width: parent.width
                        height: 40

                        Rectangle {
                            anchors.fill: parent
                            anchors.leftMargin: -8
                            anchors.rightMargin: -8
                            radius: 6
                            color: Theme.raised
                            visible: rowArea.containsMouse
                        }
                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                        MouseArea {
                            id: rowArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.editRequested(row.modelData.id)
                        }

                        Text {
                            id: dateLabel
                            anchors.verticalCenter: parent.verticalCenter
                            width: 64
                            text: row.modelData.date
                            color: Theme.faint
                            font.family: Theme.dataFont
                            font.pixelSize: 12
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: dateLabel.right
                            anchors.right: categoryLabel.left
                            anchors.rightMargin: 16
                            text: row.modelData.title
                            color: row.modelData.readable ? Theme.text : Theme.down
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            id: categoryLabel
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: amountLabel.left
                            anchors.rightMargin: 24
                            width: 180
                            text: row.modelData.category
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            id: amountLabel
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: parent.right
                            width: 140
                            horizontalAlignment: Text.AlignRight
                            text: row.modelData.amount
                            color: row.modelData.income ? Theme.up : Theme.text
                            font.family: Theme.dataFont
                            font.pixelSize: 13
                        }
                    }
                }
            }
        }
    }
}
